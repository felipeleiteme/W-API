import os
import uuid
from typing import Any, Dict

import docker
import httpx
from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field
from supabase import Client, create_client

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
  raise RuntimeError('Variáveis SUPABASE_URL e SUPABASE_KEY são obrigatórias para iniciar a API.')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
docker_client = docker.from_env()

app = FastAPI(title='MVP ZAPI-Clone')

NETWORK_NAME = 'whatsapp-mvp_zapi_network'
CONNECTOR_IMAGE = 'conector-baileys:latest'


class SendTextPayload(BaseModel):
  to: str = Field(..., description='Número do destinatário com DDI e DDD, apenas dígitos.')
  text: str = Field(..., description='Mensagem em texto puro.')


@app.post('/instance/create')
async def create_instance() -> Dict[str, Any]:
  instance_id = str(uuid.uuid4())
  try:
    supabase.table('instances').insert({'id': instance_id, 'status': 'pending'}).execute()
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f'Erro ao criar registro no Supabase: {exc}')

  container_name = f'conector-{instance_id}'

  try:
    docker_client.containers.run(
      image=CONNECTOR_IMAGE,
      name=container_name,
      network=NETWORK_NAME,
      detach=True,
      environment={
        'INSTANCE_ID': instance_id,
        'SUPABASE_URL': SUPABASE_URL,
        'SUPABASE_KEY': SUPABASE_KEY
      },
      restart_policy={'Name': 'unless-stopped'}
    )
  except docker.errors.APIError as exc:
    supabase.table('instances').update({'status': 'error'}).eq('id', instance_id).execute()
    raise HTTPException(status_code=500, detail=f'Erro ao subir contêiner do conector: {exc.explanation}')

  try:
    supabase.table('instances').update({
      'status': 'starting',
      'container_name': container_name
    }).eq('id', instance_id).execute()
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f'Erro ao atualizar instância no Supabase: {exc}')

  return {'instance_id': instance_id, 'status': 'starting'}


@app.get('/instance/{instance_id}/qr')
async def get_latest_qr(instance_id: str = Path(..., description='ID da instância retornada no create')) -> Dict[str, Any]:
  try:
    response = supabase.table('qr_codes') \
      .select('qr_string') \
      .eq('instance_id', instance_id) \
      .order('created_at', desc=True) \
      .limit(1) \
      .execute()
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f'Erro ao consultar QR Codes: {exc}')

  data = getattr(response, 'data', None) or []
  if not data:
    raise HTTPException(status_code=404, detail='QR Code ainda não gerado para esta instância.')

  return {'instance_id': instance_id, 'qr_string': data[0]['qr_string']}


@app.post('/instance/{instance_id}/send-text')
async def send_text(
  payload: SendTextPayload,
  instance_id: str = Path(..., description='ID da instância retornada no create')
) -> Dict[str, Any]:
  try:
    response = supabase.table('instances') \
      .select('container_name') \
      .eq('id', instance_id) \
      .limit(1) \
      .execute()
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f'Erro ao buscar instância no Supabase: {exc}')

  data = getattr(response, 'data', None) or []
  if not data:
    raise HTTPException(status_code=404, detail='Instância não encontrada.')

  container_name = data[0].get('container_name')
  if not container_name:
    raise HTTPException(status_code=400, detail='Instância ainda não possui um conector ativo.')

  target_url = f'http://{container_name}:3000/send-text'
  async with httpx.AsyncClient(timeout=15) as client:
    try:
      connector_response = await client.post(target_url, json=payload.model_dump())
    except httpx.RequestError as exc:
      raise HTTPException(status_code=502, detail=f'Falha ao contatar o conector: {exc}')

  if connector_response.status_code >= 400:
    raise HTTPException(status_code=connector_response.status_code, detail=connector_response.text)

  return connector_response.json()
