import express from 'express';
import pino from 'pino';
import qrcode from 'qrcode-terminal';
import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  useRemoveFileAuthState
} from '@whiskeysockets/baileys';
import { createClient } from '@supabase/supabase-js';
import { randomUUID } from 'crypto';

const { INSTANCE_ID, SUPABASE_URL, SUPABASE_KEY } = process.env;

if (!INSTANCE_ID || !SUPABASE_URL || !SUPABASE_KEY) {
  console.error('INSTANCE_ID, SUPABASE_URL e SUPABASE_KEY são obrigatórios.');
  process.exit(1);
}

const logger = pino({ level: 'info' });
const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

const app = express();
app.use(express.json());

let socket;

const formatToWhatsAppJid = (phone) => {
  if (!phone) {
    return null;
  }
  if (phone.includes('@s.whatsapp.net')) {
    return phone;
  }
  const trimmed = phone.replace(/\D/g, '');
  if (!trimmed) {
    return null;
  }
  return `${trimmed}@s.whatsapp.net`;
};

const persistQrCode = async (qr) => {
  const { error } = await supabase.from('qr_codes').insert({
    id: randomUUID(),
    instance_id: INSTANCE_ID,
    qr_string: qr
  });
  if (error) {
    logger.error({ error }, 'Falha ao salvar QR Code no Supabase');
  }
};

const updateInstanceStatus = async (status) => {
  const { error } = await supabase
    .from('instances')
    .update({ status })
    .eq('id', INSTANCE_ID);
  if (error) {
    logger.error({ error }, 'Erro ao atualizar status da instância no Supabase');
  }
};

const startBaileys = async () => {
  const { state, saveCreds } = await useRemoveFileAuthState();
  const { version } = await fetchLatestBaileysVersion();

  socket = makeWASocket({
    version,
    auth: state,
    logger,
    printQRInTerminal: false
  });

  socket.ev.on('creds.update', saveCreds);
  socket.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      qrcode.generate(qr, { small: true });
      await persistQrCode(qr);
    }

    if (connection === 'open') {
      logger.info('Conector autenticado com sucesso.');
      await updateInstanceStatus('connected');
    }

    if (connection === 'close') {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      logger.warn({ statusCode }, 'Conexão encerrada.');
      await updateInstanceStatus('disconnected');
      if (shouldReconnect) {
        setTimeout(startBaileys, 2_000);
      }
    }
  });
};

app.get('/health', (req, res) => {
  res.json({ status: 'alive', instanceId: INSTANCE_ID });
});

app.post('/send-text', async (req, res) => {
  const { to, text } = req.body || {};

  if (!socket) {
    return res.status(503).json({ error: 'WhatsApp socket não inicializado ainda.' });
  }

  if (!to || !text) {
    return res.status(400).json({ error: 'Campos "to" e "text" são obrigatórios.' });
  }

  const jid = formatToWhatsAppJid(to);
  if (!jid) {
    return res.status(400).json({ error: 'Número de destino inválido.' });
  }

  try {
    const response = await socket.sendMessage(jid, { text });
    res.json({ success: true, response });
  } catch (error) {
    logger.error({ error }, 'Erro ao enviar mensagem.');
    res.status(500).json({ error: 'Falha ao enviar mensagem para o WhatsApp.' });
  }
});

const start = async () => {
  await startBaileys();
  const port = process.env.PORT || 3000;
  app.listen(port, () => logger.info(`Conector Baileys escutando na porta ${port}`));
};

start().catch((error) => {
  logger.error({ error }, 'Erro fatal ao iniciar o conector.');
  process.exit(1);
});
