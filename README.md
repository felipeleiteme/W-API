# MVP ZAPI-Clone

Stack mínima para orquestrar conectores WhatsApp (Baileys) via FastAPI + Supabase + Docker.

## Passo 1 – Configuração do Supabase
1. Crie um projeto gratuito no [Supabase](https://supabase.com/).
2. No menu **SQL Editor**, cole o conteúdo de `init-db.sql` e execute para criar as tabelas `instances` e `qr_codes`.
3. Em **Project Settings > API**, copie `Project URL` e a `service_role key`.
4. Crie um arquivo `.env` na raiz contendo:
   ```env
   SUPABASE_URL=https://SEU-PROJETO.supabase.co
   SUPABASE_KEY=service_role_key_aqui
   ```

## Passo 2 – Build e Run (O Lançamento)
```bash
# 1. Buildar a imagem do Conector (Motor) primeiro
docker build -t conector-baileys:latest ./conector-baileys

# 2. Iniciar a API de Fachada (Cérebro) – usa variáveis do .env
docker-compose --env-file .env up -d --build
```
*A API sobe na porta 80 do host. Certifique-se de que a porta esteja livre.*

## Passo 3 – Testando o Fluxo
1. **Criar instância:** `POST http://localhost/instance/create`
   - Resposta: `{ "instance_id": "...", "status": "starting" }`
2. **Buscar QR Code:** `GET http://localhost/instance/{instance_id}/qr`
   - Escaneie o `qr_string` com o WhatsApp para autenticar o conector.
3. **Enviar mensagem:** `POST http://localhost/instance/{instance_id}/send-text`
   ```json
   { "to": "5511999999999", "text": "Olá do MVP" }
   ```

Se precisar resetar, pare e remova os serviços com `docker-compose down` e limpe os contêineres de conectores (`docker rm -f conector-...`).
