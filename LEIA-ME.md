# Clipador GTA VI

## COMEÇO RÁPIDO (sem comandos)
1. **Instalar (uma vez):** dê dois cliques em **`instalar.bat`**. Ele instala o que faltar (Python, ffmpeg, Deno), prepara o programa e cria o atalho **"Clipador GTA VI"** na área de trabalho. Se pedir, feche a janela e abra o `instalar.bat` de novo.
2. **Abrir:** dê dois cliques no atalho **"Clipador GTA VI"** (ou em `iniciar.bat`). O navegador abre sozinho com o painel. **Mantenha a janela preta aberta** enquanto usa; fechar a janela encerra o programa.
3. **Usar, tudo por cliques:**
   - **🏠 Início:** mostra se tudo está configurado.
   - **➕ Novo corte:** cole o link de uma live (encerrada ou ao vivo) e clique em *Gerar cortes*.
   - **🗼 Torre:** cadastre os canais e clique em *Ligar a Torre*.
   - **✅ Aprovação:** assista, ajuste o título e aprove ou rejeite.
   - **📤 Publicar:** envie ao YouTube e ao Instagram, e use o modo assistido do TikTok.
   - **🎞️ Compilado:** monte o vídeo de ~15 minutos.
   - **⚙️ Configurações:** conecte o YouTube, cole o token do Instagram e as chaves da Twitch/Kick.

Os arquivos de configuração (`client_secret.json`, `token.json`, `instagram_config.json`, `canais.json`) ficam na pasta do programa e **não devem ser compartilhados**.

> O restante deste guia é a **referência técnica** (como configurar cada API e os comandos avançados). No dia a dia, você não precisa dos comandos.

---

# Clipador GTA VI - Etapa 1 (Windows)

## Instalação (só uma vez)

1. **Python 3.11 ou 3.12**: baixe em https://www.python.org/downloads/ e, na instalação, **marque "Add Python to PATH"**.
2. **ffmpeg**: abra o PowerShell e rode:
   `winget install Gyan.FFmpeg`
   Depois **feche e abra o PowerShell de novo** e confira com `ffmpeg -version`.
3. Extraia esta pasta (por ex. em `C:\clipador`), abra o PowerShell nela e rode:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
   (Se der erro de permissão ao ativar: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`)

## Uso diário

Sempre comece com `venv\Scripts\activate` na pasta do projeto.

**1. Gerar os cortes** (live já encerrada ou VOD):
```
python clipador.py --url "LINK_DA_LIVE" --credito "NomeDoStreamer" --quantidade 10
```
**Live ainda ao vivo** (grava 30 min do início e processa):
```
python clipador.py --url "LINK_DA_LIVE" --credito "NomeDoStreamer" --minutos-live 30
```
**Vídeo que você já baixou:** troque `--url "..."` por `--arquivo "C:\caminho\live.mp4"`.

Opções úteis:
- `--sem-legenda` : bem mais rápido (pula a transcrição). Recomendado para testar.
- `--idioma pt` (ou `en`) : acelera e melhora a legenda se você souber o idioma.
- `--sem-horizontal` : não gera a versão 16:9 (então não entra no compilado).

**2. Aprovar** (abre no navegador):
```
streamlit run painel.py
```
Assista, ajuste título/crédito/hashtags e clique em Aprovar ou Rejeitar.

**3. Compilado de ~15 min** (com os aprovados, até 30 cortes):
```
python compilado.py
```
Sai em `compilados\` o vídeo + um `.txt` com capítulos e créditos para colar na descrição.

## Dicas para o seu PC (i3, 8 GB)
- Rode **uma live por vez** e feche outros programas pesados.
- Lives longas ocupam disco: depois de gerar os cortes, apague os arquivos da pasta `work\`.
- Primeiro rode com `--sem-legenda` para validar os momentos; depois rode com legenda.

## Direitos autorais
Os vídeos são de outros criadores. Peça autorização, mantenha o crédito visível e use a aprovação manual para filtrar o que não deve ser publicado.


## Etapa 2 - Postar no YouTube

### Configuração (uma vez, ~10 min, gratuito)
1. Atualize as bibliotecas: `pip install -r requirements.txt`
2. Acesse https://console.cloud.google.com e crie um **projeto novo**.
3. Menu **APIs e serviços > Biblioteca**: ative **YouTube Data API v3** e **YouTube Analytics API**.
4. **Tela de permissão OAuth**: tipo **Externo**, preencha o nome do app e seu e-mail e, em **Usuários de teste**, adicione o e-mail do seu canal.
5. **Credenciais > Criar credenciais > ID do cliente OAuth > Aplicativo para computador**. Baixe o JSON, renomeie para `client_secret.json` e coloque na pasta do projeto.
6. Rode `python postar_youtube.py --teste` para ver o que seria postado.

### Uso
```
python postar_youtube.py                 # posta os Shorts aprovados (até 6 por execução), como PRIVADO
python postar_youtube.py --publico       # como público
python postar_youtube.py --compilado compilados\compilado_XXXX.mp4 --titulo "Seu título"
```
Na primeira execução abre o navegador: faça login com a conta do canal e autorize. Os postados vão para `clips\postados` com o link salvo no `meta.json`.

### Limites que você precisa saber
- **Cota:** cada upload custa 1.600 das 10.000 unidades diárias, então cabem **~6 vídeos por dia**. Se estourar, o script avisa e você continua no dia seguinte.
- **Vídeos "privados":** projetos novos e não auditados da API só conseguem postar como privado. Você pode publicar manualmente no YouTube Studio (leva segundos) ou pedir a **auditoria de conformidade da API** no Google (formulário gratuito, pode demorar dias).
- **Token expira em 7 dias** enquanto o app está em modo "Teste": é só autorizar de novo (apague `token.json`). Para evitar, mude o app para "Em produção" na tela de permissão.
- **Aumento de cota** também se pede por formulário ao Google, com justificativa.


## Etapa 3 - Postar no Instagram (Reels)

O Instagram **publica na hora e como público** (a API não tem "privado"). Por isso o script pede confirmação antes de enviar.

### Configuração (uma vez)
1. **Conta Instagram profissional (Business):** no app, *Configurações > Tipo de conta e ferramentas > Mudar para conta profissional > Empresa*. A API de publicação funciona com Business (Creator pode não ser aceita).
2. Acesse **developers.facebook.com**, entre com seu Facebook e crie um **app** (tipo *Empresa/Business*).
3. No app, adicione o produto **Instagram** e abra *API com login do Instagram* (*Instagram API setup with Instagram login*).
4. Em *Funções do app*, adicione sua conta do Instagram como **testador do Instagram**. Aceite o convite no app do Instagram (*Configurações > Apps e sites > Convites de testador*).
5. No painel do produto Instagram, clique em **Gerar token** para a sua conta, autorize as permissões `instagram_business_basic` e `instagram_business_content_publish` e **copie o token e o ID da conta**.
6. Copie `instagram_config.exemplo.json` para `instagram_config.json` e cole o `ig_user_id` e o `access_token`.

### Uso
```
python postar_instagram.py --teste          # só mostra o que seria postado
python postar_instagram.py                  # pede confirmação e posta (máx. 5 por execução)
python postar_instagram.py --renovar-token  # o token vale ~60 dias; renove antes de vencer
```
Se algum passo falhar, o script mostra a resposta de erro da Meta: copie e me envie.

### Observações
- Em modo de desenvolvimento, o app só publica nas contas que têm função nele (a sua), o que é suficiente aqui.
- Limite da API: 100 posts por 24 h, muito acima do que você vai usar.
- Para não parecer spam, não poste todos os cortes de uma vez: use `--max 3` e espaçe ao longo do dia.
- O YouTube e o Instagram agora **não movem** os cortes: eles só marcam o link no `meta.json`, e cada script pula o que já foi postado naquela plataforma.

## Próximas etapas
TikTok, analytics e detecção por chat.

### Atualização: apps novos da Meta usam "Login unificado"
Apps criados recentemente não oferecem mais a "API com login do Instagram", só a **"API setup with Unified login"** (e a do login do Facebook). Nesse caso:
- No `instagram_config.json`, use `"host": "https://graph.facebook.com"` (já é o padrão do exemplo).
- O token do login unificado é de "usuário do sistema" e, em geral, **não expira** (não precisa renovar).
- Para descobrir o `ig_user_id` a partir do token: `python postar_instagram.py --descobrir-conta`.

## Etapa 4 - TikTok (modo assistido)
A API do TikTok só publica como privado até o app passar por auditoria, então o painel (`streamlit run painel.py`) ganhou a aba **🎵 Postar no TikTok**: para cada corte aprovado você baixa o vídeo, copia a legenda pronta (ícone de copiar) e envia pelo **TikTok Studio** (tiktok.com/tiktokstudio/upload), que também permite agendar. Depois clique em "Marcar como postado". A aba **📋 Status** mostra o que já foi para cada plataforma.

## Etapa 5 - Modo AO VIVO (`ao_vivo.py`)
Grava a live enquanto ela acontece e gera cortes **assim que surge um momento forte** (atraso de ~1 a 2 minutos). Os cortes aparecem sozinhos no painel para aprovação.

```
python ao_vivo.py --url "LINK_DA_LIVE" --credito "NomeDoStreamer"
```
Pare com **Ctrl+C**: ele termina de renderizar o que estiver na fila.

Como funciona: grava o stream em `work\live_*.ts`, a cada 30 s analisa o áudio novo e compara com o "volume normal" **daquela live** (por isso os primeiros 3 minutos são só de aprendizado). Quando a nota passa do limiar, o corte entra numa fila e é renderizado em segundo plano.

Ajustes:
- `--limiar 4.0`: nota mínima. **Menor = mais cortes** (ex.: 3), **maior = só os mais fortes** (ex.: 6). O terminal mostra a "maior nota" de cada ciclo, então você vê se o limiar está alto demais. Calibre nos primeiros minutos.
- `--max-por-hora 12`: teto de cortes por hora.
- `--aquecimento 180`: segundos iniciais só aprendendo o volume normal.
- `--com-legenda`: transcreve cada corte (pesado para o seu PC; use só se der conta).
- `--intervalo 30`: de quantos em quantos segundos analisa.

Observações:
- Funciona com links de **YouTube, Twitch e Kick** ao vivo (usa o `yt-dlp`). Grava a partir do momento em que você inicia, não do começo da live (para o começo, use o modo `--minutos-live` do `clipador.py`).
- A gravação ocupa ~2 GB por hora (720p). **Apague `work\live_*.ts` depois.**
- **Uma live por vez** no seu PC. Para várias lives, abra um PowerShell por live, mas só se o PC aguentar (a renderização é o que pesa).
- Cortes muito próximos (menos de 60 s entre si) são descartados para não repetir o mesmo momento.

## Problema: "No supported JavaScript runtime" / "Requested format is not available" (YouTube)
Desde fim de 2025 o YouTube exige que o yt-dlp tenha um **motor de JavaScript** instalado. Sem ele, os formatos de vídeo não aparecem. Solução (uma vez):
1. No PowerShell: `winget install --id=DenoLand.Deno`
2. **Feche e abra o PowerShell** (para o Windows reconhecer o Deno).
3. Com o ambiente ativo (`venv\Scripts\activate`): `pip install -U "yt-dlp[default]"`
4. Teste: `yt-dlp --version` e `deno --version`, depois rode o `ao_vivo.py` de novo.

Se você já tem o **Node.js** instalado, os scripts o usam automaticamente quando não há Deno. O YouTube muda com frequência: se um link que funcionava parar de funcionar, rode `pip install -U "yt-dlp[default]"` antes de qualquer outra coisa.

## Etapa 6 - TORRE DE CONTROLE (`torre.py`)
A Torre vigia os canais que **você escolhe** (Twitch, Kick e YouTube), mostra quem está ao vivo e quantos espectadores,
detecta sinais de momento forte e **liga sozinha o modo ao vivo** (gravação + cortes) nas lives mais assistidas.
Tudo aparece na aba **🗼 Torre de Controle** do painel, que atualiza sozinha a cada 15 s.

### Configuração
1. `pip install -r requirements.txt` (agora inclui `websockets`, usado para ler o chat da Twitch).
2. Copie `canais.exemplo.json` para `canais.json` e edite a lista `canais`:
   - **Twitch:** `"id"` = nome do canal na URL (twitch.tv/**gaules** → `gaules`).
   - **Kick:** `"id"` = nome na URL (kick.com/**xqc** → `xqc`).
   - **YouTube:** `"id"` = o @ do canal (`@nomedocanal`). O canal precisa estar com a live aberta ao público.
   - `"nome"` = como aparece no painel e no crédito do corte. `"gravar": false` = só monitora, nunca grava.
3. **(Recomendado) Chaves de API gratuitas** — sem elas a Torre usa o yt-dlp, que funciona mas é mais lento e dá menos informação:
   - **Twitch:** dev.twitch.tv/console > *Register Your Application* (URL de redirecionamento: `http://localhost`, categoria *Application Integration*, tipo *Confidential*) > *New Secret*. Copie *Client ID* e *Client Secret* para `"twitch"` no `canais.json`. (A Twitch exige verificação em duas etapas na conta.)
   - **Kick:** kick.com/settings/developer > criar app (URL de redirecionamento: `http://localhost`) e copie *Client ID* e *Secret* para `"kick"`.
   - Essas chaves são só leitura de dados públicos. **Não compartilhe o `canais.json` depois de preenchido.**

### Uso
```
python torre.py --uma-vez      # testa a configuração com uma checagem só
python torre.py                # monitora e grava; deixe rodando durante os lançamentos
python torre.py --sem-gravar   # só monitora (não grava nada)
streamlit run painel.py        # em outro PowerShell: veja a Torre, aprove os cortes
```
Para parar: **Ctrl+C**. A Torre espera as gravações terminarem de renderizar os cortes.

### O que a Torre faz
- **Checagem** de todos os canais a cada `intervalo_seg` (padrão 120 s). Twitch e Kick pela API oficial (todos os canais em 1 chamada); YouTube pelo yt-dlp, a cada `intervalo_youtube_seg` (300 s).
- **Sinais de momento** (aparecem em "Momentos"): salto de espectadores (+30% e +150 entre checagens) e explosão do chat da Twitch (3x o normal e pelo menos 30 msg/min). Ajustáveis em `"deteccao"`.
- **Gravação automática:** liga o `ao_vivo.py` nas lives mais assistidas, até `gravar_no_maximo` ao mesmo tempo (**no seu i3, deixe em 1 ou 2**). Os cortes caem na aba Aprovação.
- **Esteira:** Sinal → Renderizando → Aguardando aprovação → Aprovado → Postado.
- Logs de cada gravação em `logs\`. Gravações com mais de 24 h em `work\` são apagadas sozinhas.

### Cuidados
- Cada gravação ocupa ~2 GB/hora e a renderização pesa no PC: com 2 gravações juntas, o PC pode ficar lento. Comece com `"gravar_no_maximo": 1`.
- O chat de **Kick e YouTube ainda não é lido** (só espectadores e áudio nesses). Na Twitch, os sinais de chat ficam registrados, mas por enquanto **não** mudam a nota do corte (isso entra na próxima etapa, "replay do chat").
- Escolha canais **que permitem clipes** ou com os quais você combinou. Os créditos já saem no vídeo e na legenda.


## Etapa 7 - Leitura de chat (Twitch, Kick e YouTube)
A Torre agora lê o **chat de todas as plataformas** (só leitura, sem login) e registra um sinal de momento forte quando o chat explode (3x o normal do canal e pelo menos 30 mensagens/min; ajustável em `"deteccao"` no `canais.json`). Também guarda o total de mensagens **por minuto** no banco (`torre.db`), base para a próxima etapa, que é usar o chat na nota dos cortes.

- **Twitch:** conexão anônima ao chat (IRC). É a mais estável.
- **YouTube:** consulta periódica do chat da live, sem gastar a cota da API. Depende do formato interno do YouTube, que pode mudar.
- **Kick:** conexão ao chat público. Precisa descobrir o "ID da sala" de cada canal, e a Kick protege essa consulta. O instalador tenta instalar o componente opcional `curl_cffi`, que melhora muito a chance de funcionar.

**Para testar cada plataforma** (Torre > *Testar a leitura de chat*): escolha a plataforma, informe o canal (ou o link da live, no YouTube), os segundos, e clique em *Testar leitura de chat*. O resultado mostra quantas mensagens foram lidas. Pelo comando: `python chat.py --testar twitch:gaules kick:xqc "youtube:LINK_DA_LIVE" --segundos 40`.

Em **Torre > Meus canais** você liga ou desliga a leitura de chat de cada plataforma.

## Visual do painel
O painel ganhou tema escuro, cartões de lives, esteira de produção e lista de verificação. O tema fica em `.streamlit\config.toml` e `estilo.py`.


## Etapa 8 - Mais cortes e gravação à prova de falhas (modo ao vivo)
- **Explosão do chat vira corte:** quando a Torre detecta o chat explodindo em um canal que está sendo gravado, o modo ao vivo gera um corte desse momento (o instante é ajustado alguns segundos antes, porque o chat reage depois do lance). O sinal na Torre passa a mostrar a situação do corte (Renderizando, Aguardando aprovação...).
- **Corte garantido:** se nenhum corte sair em `--garantir` minutos (padrão **10**), o sistema corta o melhor momento da janela mesmo abaixo do limiar, para você nunca ficar sem material. Para desligar: `"--garantir", "0"` em `"ao_vivo_extra"` do `canais.json`.
- **Gravação à prova de falhas:** se o ffmpeg não informar o progresso, o tempo gravado passa a ser estimado pelo relógio. Se o arquivo parar de crescer por 2 minutos (live caiu ou stream travou), a gravação encerra com um aviso claro e a Torre a religa sozinha em ~90 s se a live continuar.
- **Diagnóstico no log:** cada linha mostra o tamanho da gravação (por exemplo `| gravação: 85 MB`). Se o número não aumenta, o problema está na captura do stream.
- Quando uma gravação termina, a Torre registra no log o código de saída (`0` = normal).


## Etapa 9 - Captura de live com vários métodos (e botão de teste)
Para gravar uma live ao vivo, o sistema agora tenta **três métodos, nesta ordem**, até um deles começar a gravar de verdade (arquivo crescendo em até 45 s):
1. **yt-dlp baixando a live** por conta própria (o mais compatível, usa a mesma lógica do download de lives encerradas);
2. **ffmpeg direto** no endereço do stream;
3. **ffmpeg imitando um navegador** (com cabeçalhos), para plataformas que bloqueiam o acesso direto.

Para forçar um método, use `"--metodo", "ytdlp"` (ou `"ffmpeg"`) em `"ao_vivo_extra"` no `canais.json`. O padrão é `auto`.

O log mostra qual método funcionou (`✔ Gravando com: ...`) e, para os que falharam, **as mensagens de erro reais** do programa.

**Testar uma live em ~1 minuto:** na aba 🗼 Torre, abra **🎥 Testar a gravação de uma live**, cole o link de uma live que esteja ao vivo e clique em *Testar gravação*. Procure por `TESTE OK` no resultado. Pelo comando: `python ao_vivo.py --url "LINK" --so-testar`.

Se a gravação parar de crescer por 2 minutos depois de começar, ela encerra com **código 3** e a Torre a religa em ~90 s (repetindo a escolha do método).

> Correção: versões anteriores passavam ao ffmpeg opções de reconexão (`-reconnect`) que, em streams HLS, faziam ele reconectar em loop ("Will reconnect ... End of file") e nunca gravar. Isso foi removido.
