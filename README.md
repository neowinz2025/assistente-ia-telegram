# Bot Telegram - Integração IDDAS & Leitor de Bilhetes em PDF

Este projeto implementa um Bot de Telegram que recebe os dados de emissão de passagens aéreas (Cliente, Fornecedor, Valor de Venda, Valor de Custo) juntamente com o bilhete/reserva anexo em formato PDF, faz a leitura e extração automática de dados dos voos e cadastra tudo no sistema **IDDAS Agência** via API REST.

Ele pode ser executado **localmente (polling)** ou implantado de forma **100% gratuita na Vercel (Webhook)**.

---

## ☁️ Como Rodar na Vercel (Gratuito & Serverless)

### 1. Envie o Código para o GitHub
Suba a pasta deste projeto para um repositório no seu GitHub.

### 2. Importe na Vercel
1. Acesse o painel da [Vercel](https://vercel.com) e clique em **Add New > Project**.
2. Selecione o repositório do GitHub.
3. Em **Environment Variables**, adicione as seguintes variáveis:
   - `TELEGRAM_BOT_TOKEN`: O token do seu Bot do Telegram
   - `IDDAS_API_KEY`: Sua chave de API do IDDAS
   - `IDDAS_BASE_URL`: `https://apiagencia.iddas.com.br/api/v1`
4. Clique em **Deploy**.

### 3. Ativar o Webhook no Telegram
Após o deploy, a Vercel fornecerá uma URL pública (ex: `https://meu-bot-iddas.vercel.app`).

No seu terminal local, execute:
```bash
python set_webhook.py https://meu-bot-iddas.vercel.app
```
 Pronto! Agora qualquer mensagem enviada para o seu Bot no Telegram será processada instantaneamente na nuvem pela Vercel.

---

## 💻 Como Rodar Localmente (Polling)

### 1. Instale as Dependências
```bash
pip install -r requirements.txt
```

### 2. Configuração do `.env`
Preencha o arquivo `.env`:
```env
TELEGRAM_BOT_TOKEN=seu_token_do_telegram_aqui
IDDAS_API_KEY=sua_chave_de_api_iddas_aqui
IDDAS_BASE_URL=https://apiagencia.iddas.com.br/api/v1
```

### 3. Execute o Bot
```bash
python main.py
```

---

## 📩 Estrutura da Mensagem no Telegram

Envie a mensagem no Telegram no seguinte padrão, **anexando o arquivo PDF da reserva/bilhete**:

```text
Anexo - PDF da reserva

Dados do cliente 
Nome: João Silva
CPF: 123.456.789-00
Data de Nascimento: 15/08/1990
E-mail: joao@email.com
Tel: 11999887766

Dados do fornecedor 
Nome: Cia Gol
CPF/CNPJ: 07.575.651/0001-59
Tel: 1130000000

Valor da venda: R$ 1.500,00
Valor de custo: R$ 1.100,00
```
