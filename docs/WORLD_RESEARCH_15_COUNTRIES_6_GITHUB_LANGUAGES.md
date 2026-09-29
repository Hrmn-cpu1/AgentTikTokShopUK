# Pesquisa mundial: 15 países + 6 rodadas GitHub

Data da pesquisa: 29 set. 2026. Escopo: arquitetura de agentes e fluxos de conteúdo curto; nenhum código foi alterado até a conclusão das rodadas. Uma rodada nacional significa consultas e leitura focadas em um país; as respostas do mecanismo de busca às vezes retornaram projetos globais. Isso é registrado como limite, não como evidência de adoção local.

## Classificação

- **OFFICIAL**: documentação/API publicada pelo titular da plataforma ou pela documentação técnica do framework.
- **OSS/STABLE**: projeto aberto com código e interfaces reproduzíveis; “stable” descreve o padrão/tecnologia, não garante suporte do mantenedor.
- **OSS/EXPERIMENTAL**: protótipo, projeto recente ou dependente de modelos/serviços externos.
- **UNOFFICIAL**: integração sem uma API pública documentada para essa finalidade.
- **BROWSER AUTOMATION**: controle de interface web por navegador.
- **REVERSE ENGINEERED**: endpoints, assinaturas ou formatos privados inferidos.
- **UNSAFE/BYPASS**: roubo/reutilização de credenciais, evasão anti-bot/CAPTCHA, falsificação de fingerprint, abuso de API privada, engajamento falso ou spam. Estudado apenas para identificar e excluir riscos.

## A — 15 rodadas nacionais

### 01 — Estados Unidos 🇺🇸

- **Problema investigado:** confiabilidade de agentes que chamam modelos/ferramentas, geração de short-form, entregas sociais e execução móvel.
- **Soluções/padrões encontrados:** documentação oficial de Content Posting separa consultar capacidades do criador, consentimento, envio e estado; Android recomenda trabalho persistente com backoff e constraints. Projetos de short-form usam pipeline assíncrono, prévia humana e FFmpeg.
- **Fontes/projetos:** [TikTok Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post) (**OFFICIAL**); [Android WorkManager](https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started/define-work) (**OFFICIAL**); [YTTT](https://github.com/FoxLabs65/YTTT) (**OSS/EXPERIMENTAL**, aprovação antes de upload); [TikTok uploader issue 238](https://github.com/wkaisertexas/tiktok-uploader/issues/238) (**BROWSER AUTOMATION**, falha após clicar Post).
- **Falhas comuns:** o clique no botão Post pode terminar em erro sem post; retry cego duplica possível efeito externo; nomes “autopilot” não provam execução ponta a ponta.
- **Ideias úteis:** status da plataforma separado de “intent enviado”; retry só depois de reconciliar efeito; revisão criativa entre render e entrega.
- **Não usar:** extrair cookies/identificadores ou mascarar navegador para superar bloqueios (**UNSAFE/BYPASS**).
- **Aplicação AgentTikTok:** manter a publicação humana, reportar estados comprováveis e preservar a máquina de estados no servidor.

### 02 — China 🇨🇳

- **Problema investigado:** sistemas de produção de Douyin, análise de sinais curtos e workflows multi-etapa, sem assumir equivalência com TikTok internacional.
- **Soluções/padrões encontrados:** projetos de Douyin mostram arquivos de projeto com roteiro/cenas/ativos, tarefas persistidas, retomar geração, workers Celery/Redis e estados explícitos. Projetos de captura usam dados e assinaturas de web privados.
- **Fontes/projetos:** [MovieFlow](https://github.com/wordflowlab/movieflow) (**OSS/EXPERIMENTAL**, checkpoint/retomada); [short-video-factory](https://github.com/lppmql/short-video-factory) (**OSS/EXPERIMENTAL**, fila e estados); [GoVideo](https://github.com/kiritosuki/GoVideo) (**OSS/EXPERIMENTAL**, outbox e consumo idempotente); [Douyin_TikTok_Download_API troubleshooting](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/main/documents/zh/14-troubleshooting.md) (**REVERSE ENGINEERED**, evidencia forte de dependência de sessão/assinatura).
- **Falhas comuns:** sessão, assinatura, proxy ou alteração de protocolo causam respostas vazias/falsas; processo de transcodificação pode deixar processos FFmpeg pendurados.
- **Ideias úteis:** armazenamento do estado por estágio, saída intermediária reproduzível, retry delimitado e diagnóstico explícito.
- **Não usar:** assinatura privada, fingerprint spoofing ou rotas Douyin como se fossem APIs TikTok internacional (**REVERSE ENGINEERED/UNSAFE**).
- **Aplicação AgentTikTok:** reaproveitar padrão de retomada e fila; nenhum endpoint Douyin usado como provedor internacional.

### 03 — Japão 🇯🇵

- **Problema investigado:** conversão de roteiro em vídeo vertical e adaptação de ferramentas OSS para fluxo de criação.
- **Soluções/padrões encontrados:** repositório traduzido em japonês de MoneyPrinterTurbo descreve tema → roteiro → correspondência de material → voz/legendas/música; autores japoneses descrevem usar referência viral para abstrair estrutura visual e não reutilizar a filmagem original.
- **Fontes/projetos:** [MoneyPrinterTurbo README-ja](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/README-ja.md) (**OSS/EXPERIMENTAL**); [análise de estrutura visual no Zenn](https://zenn.dev/beatapi/articles/f2ead956ee00c4) (relato técnico; padrões criativos, não framework); [TikTok OpenSDK Android](https://github.com/tiktok/tiktok-opensdk-android) (**OFFICIAL**).
- **Falhas comuns:** automação de publicação é frequentemente confundida com exportação de vídeo; render local depende de fontes, codecs e binários presentes.
- **Ideias úteis:** localizar texto e narração por idioma; decompor referência em ritmo/hook, sem copiar mídia protegida.
- **Não usar:** raspar conteúdo como biblioteca de assets ou misturar scopes do OpenSDK com envio/publicação.
- **Aplicação AgentTikTok:** roteiro pt-BR e legenda temporizada são artefatos separados; só reutilizar princípios visuais abstratos.

### 04 — Coreia do Sul 🇰🇷

- **Problema investigado:** termos locais para pipeline de short-form, automação de conteúdo, fila e apps Android.
- **Soluções/padrões encontrados:** a pesquisa em coreano não encontrou um repositório TikTok/short-form local com evidência suficiente para afirmar maturidade regional; a documentação oficial Android coreana apresenta WorkManager como componente para execução diferida/persistente.
- **Fontes/projetos:** [WorkManager codelab em coreano](https://developer.android.com/codelabs/android-workmanager?hl=ko) (**OFFICIAL**); código aberto de renderização considerado adiante nas rodadas de idioma.
- **Falhas comuns:** amostra local de repos foi fraca; alegações de “viral” em ferramentas não equivalem a métricas disponíveis ou validadas.
- **Ideias úteis:** usar execução gerida pelo sistema e tolerar constraints/reinício em vez de manter serviço contínuo sem necessidade.
- **Não usar:** afirmar tendências da Coreia ou disponibilidade TikTok com base em buscas globais.
- **Aplicação AgentTikTok:** sem mudança de geografia: BR continua explícito; WorkManager só se surgir tarefa móvel diferida necessária.

### 05 — Reino Unido 🇬🇧

- **Problema investigado:** workflow creator/social em ambiente UK, APIs TikTok e entrega automatizada.
- **Soluções/padrões encontrados:** projetos de recorte e vídeo curto externalizam análise, roteiro, assets, montagem e publicação; Content Posting API documenta upload e Direct Post distintos.
- **Fontes/projetos:** [TikTok Direct Post docs](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post) (**OFFICIAL**); [openshorts](https://github.com/Serialabs/openshorts) (**OSS/EXPERIMENTAL**, fila e render, integrações terceirizadas); [OpenMontage](https://github.com/fivetaku/openmontage) (**OSS/EXPERIMENTAL**, pipeline com aprovação e checkpoint).
- **Falhas comuns:** declarar post concluído a partir de exportação ou abertura do compositor; dependência de upload provider encoberta por interface “autopublish”.
- **Ideias úteis:** lifecycle claro, manifesto por vídeo, proveniência de mídia e portões de aprovação/custo.
- **Não usar:** inferir aprovação ou escopos da conta do proprietário com base no repositório.
- **Aplicação AgentTikTok:** sinalizar claramente `LOCAL_RENDERED`, `HANDOFF_INITIATED` e `PUBLISHED` como evidências diferentes.

### 06 — Alemanha 🇩🇪

- **Problema investigado:** automação de produção curta, FFmpeg e fluxos com fila e recuperação.
- **Soluções/padrões encontrados:** exemplos de automação n8n encadeiam feed/RSS, pesquisa factual, roteiro por cenas, geração, montagem FFmpeg e caption por plataforma; código aberto usa jobs e saídas legíveis.
- **Fontes/projetos:** [pipeline n8n de vídeo (DE)](https://heiner.io/labor/n8n-video-automatisierung) (relato operacional, não comprovação independente); [OpenMontage](https://github.com/fivetaku/openmontage) (**OSS/EXPERIMENTAL**); [Android persistent work](https://developer.android.com/develop/background-work/background-tasks/persistent) (**OFFICIAL**).
- **Falhas comuns:** custo e tempo de vídeo generativo ficam escondidos; orquestração de workflow vira um script único difícil de retomar.
- **Ideias úteis:** tarefas assíncronas com estágios e tracking de custo por execução.
- **Não usar:** cópia de clips ou reprocessamento para contornar direitos/regras de plataforma.
- **Aplicação AgentTikTok:** guardar cenas e metadados dentro do experimento; sem comprar um serviço de vídeo externo por padrão.

### 07 — França 🇫🇷

- **Problema investigado:** ferramentas abertas de vídeo curto, cadeia IA→edição e saída social.
- **Soluções/padrões encontrados:** pesquisa em francês localizou principalmente workflows de criação e projetos globais; fontes mais confiáveis reforçam perfil de tarefa durável e render por stages, não estatísticas nacionais de plataforma.
- **Fontes/projetos:** [mcp-video](https://github.com/eg-ethan/mcp-video) (**OSS/EXPERIMENTAL**, ferramentas FFmpeg estruturadas e limites); [TikTok content sharing guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines) (**OFFICIAL**).
- **Falhas comuns:** confundir dados agregados de pesquisa com API comercial acessível; documentação de produto de terceiros muda mais rápido que os contratos de plataforma.
- **Ideias úteis:** ferramentas atômicas de edição com parâmetros validados e qualidade por cena.
- **Não usar:** integração de publicação não oficial só porque uma plataforma de gestão oferece API.
- **Aplicação AgentTikTok:** reter nosso renderer determinístico e validação de contrato; sem novas integrações externas.

### 08 — Espanha 🇪🇸

- **Problema investigado:** geração de Reels/Shorts/TikTok, cortes e ferramentas de produção em espanhol.
- **Soluções/padrões encontrados:** tutorial GitHub em espanhol replica pipeline real de inbox → transcrição → cortes/legendas → agendamento multiplataforma; componentes Remotion/Whisper/FFmpeg são separados.
- **Fontes/projetos:** [tutorial-pipeline-reels](https://github.com/Drignacioalcala/tutorial-pipeline-reels) (**OSS/EXPERIMENTAL**, tutorial declarado pelo autor); [mcp-video](https://github.com/eg-ethan/mcp-video) (**OSS/EXPERIMENTAL**); [ai-content-pipeline](https://github.com/roccopaz/ai-content-pipeline) (**OSS/EXPERIMENTAL**, log de clips e revisão).
- **Falhas comuns:** “viral moment” é score heurístico; projeto com poucas contribuições não demonstra qualidade ou publicação durável.
- **Ideias úteis:** inbox de assets, transcrição com timecode, clipe em draft e ledger da decisão.
- **Não usar:** gravar métricas inexistentes ou repostar a fonte.
- **Aplicação AgentTikTok:** manter os componentes asset plan, guião, scene plan, SRT, render e evidence ledger separados.

### 09 — Brasil 🇧🇷

- **Problema investigado:** mercado de operação, descobrimento de sinais BR, fluxo de conteúdo pt-BR e regras de IA/postagem.
- **Soluções/padrões encontrados:** TikTok Next oferece tendências de negócio e ferramentas da plataforma; Research API não é um feed comercial aberto: candidatura é reservada a organizações/objetivo elegíveis. TikTok exige identificação de conteúdo realista gerado por IA. Em OSS local, uma ferramenta Android offline de edição oferece auto-pan/FFmpeg, e repositórios de short-form destacam TTS/SRT pt-BR.
- **Fontes/projetos:** [TikTok Next 2026 BR](https://ads.tiktok.com/business/pt-BR/next) (**OFFICIAL**, sinal editorial de tendência); [Research API BR](https://developers.tiktok.com/pt-BR/products/research-api) (**OFFICIAL**, elegibilidade restrita); [AI-generated content help](https://support.tiktok.com/pt_BR/using-tiktok/creating-videos/ai-generated-content) (**OFFICIAL**); [Clipper-Mobile](https://github.com/crediblemark-official/Clipper-Mobile) (**OSS/EXPERIMENTAL**).
- **Falhas comuns:** Google Trends é demanda de pesquisa, não tendência/engajamento TikTok; relatórios editoriais não fornecem API/contagem em tempo real; vídeo automático de imagem estática parece slideshow; legenda grande contínua perde sincronização.
- **Ideias úteis:** atribuir `BR_SIGNAL` e `GLOBAL_SIGNAL`; nunca preencher views/likes por aproximação; pt-BR na voz, frase curta e cortes por cena; consentimento/rotulagem de IA quando aplicável.
- **Não usar:** copiar vídeo, som, watermark, ou chamar “viral TikTok” um assunto do Google Trends.
- **Aplicação AgentTikTok:** manter Google Trends sob rótulo search interest; reservar fonte por categoria/país e registrar collection time; provenance fora do quadro do vídeo.

### 10 — Índia 🇮🇳

- **Problema investigado:** padrões OSS de processamento assíncrono e Android em contexto no qual dados TikTok atuais não representam bem o mercado local.
- **Soluções/padrões encontrados:** pesquisa local retornou projetos globais escritos por desenvolvedores indianos para Celery/Redis/FFmpeg e filas de clipes; nenhum é prova de disponibilidade/regra do TikTok na Índia.
- **Fontes/projetos:** [TimmyAICLIPs](https://github.com/Foxxyweb/TimmyAICLIPs) (**OSS/EXPERIMENTAL**, fila Celery/Redis/FFmpeg); [n8n faceless-video workflow](https://github.com/sachinkmahapure/n8n-workflow-faceless-video-ai-agent) (**OSS/EXPERIMENTAL**).
- **Falhas comuns:** selecionar serviço regional ou tendência por conteúdo traduzido em inglês; custo de processamento simultâneo e rate limits.
- **Ideias úteis:** semáforo de concorrência, estado de job, retry por etapa e cache de voz/asset para evitar gasto repetido.
- **Não usar:** inferir disponibilidade do TikTok na Índia nem comprar sinais atuais do país com dado global.
- **Aplicação AgentTikTok:** aplicar somente os padrões de worker; mercado continua Brasil.

### 11 — Indonésia 🇮🇩

- **Problema investigado:** ferramentas de creator, edição vertical e operações curtas em indonésio.
- **Soluções/padrões encontrados:** resultados locais identificaram ferramenta offline Android para clipping 9:16/auto-pan e pipelines de recorte que explicitam FFmpeg, fila e formato de saída.
- **Fontes/projetos:** [Clipper-Mobile](https://github.com/crediblemark-official/Clipper-Mobile) (**OSS/EXPERIMENTAL**, projeto com README bahasa); [TimmyAICLIPs](https://github.com/Foxxyweb/TimmyAICLIPs) (**OSS/EXPERIMENTAL**, documentação em indonésio; FastAPI/Celery/Redis).
- **Falhas comuns:** um renderer móvel local disputa CPU/memória/bateria; manter geração longa em processo de interface torna cancelamento/reinício frágeis.
- **Ideias úteis:** preview e edição no telefone são diferentes de geração longa; usar Android como control plane e backend como fonte durável.
- **Não usar:** scraping ou login reutilizado para publicar.
- **Aplicação AgentTikTok:** o APK inicia e visualiza; Railway/pipeline guarda a execução e artefatos.

### 12 — Vietnã 🇻🇳

- **Problema investigado:** geração de conteúdo curto em vietnamita, TTS, motion graphics e composição FFmpeg.
- **Soluções/padrões encontrados:** repositórios locais convertem tópico/URL em roteiro, voz vietnamita, motion graphics e MP4; foco em vídeo 9:16 e retentativa seletiva de assets.
- **Fontes/projetos:** [auto-video-gen](https://github.com/Cuongyd196/auto-video-gen) (**OSS/EXPERIMENTAL**, pipeline local); [AI-auto-generate-video](https://github.com/huytranvan2010/AI-auto-generate-video) (**OSS/EXPERIMENTAL**).
- **Falhas comuns:** suporte TTS local gratuito pode depender de serviço não contratual; assets externos podem não ter licença/atribuição clara; redownload/redownload de tudo desperdiça tempo.
- **Ideias úteis:** fazer cache por artefato, preservar texto e áudio para rerender parcial, Q/A de idioma antes da composição.
- **Não usar:** classificar idioma/região a partir do nome da fonte ou de tradução automática.
- **Aplicação AgentTikTok:** adicionar proveniência e regeneração por etapa sem adotar idioma/localidade fora do escopo.

### 13 — Tailândia 🇹🇭

- **Problema investigado:** creator tools, produção mobile e edição curta com fala/caption em tailandês.
- **Soluções/padrões encontrados:** CapCut apresenta fluxo integrado roteiro→vídeo→legenda→export; repositório tailandês de editor automatizado usa Whisper, FFmpeg e legenda editável. Isso é padrão de workflow, não evidência de API pública de postagem.
- **Fontes/projetos:** [CapCut creator workflow TH](https://www.capcut.com/th-th/resource/ai-tools-creator-workflow-thailand) (produto comercial); [ai-video-editor](https://github.com/Chirayut001/ai-video-editor) (**OSS/EXPERIMENTAL**, captions Thai/English, subtitle editor).
- **Falhas comuns:** transcrição/captions precisam revisão; aceleração CUDA/Docker não existe em todo runtime; saída atraente não equivale a entrega TikTok.
- **Ideias úteis:** editar a camada de caption antes de queimar no vídeo; fazer QA visual nos safe zones.
- **Não usar:** tratar ferramenta de edição como autorização para automatizar postagem.
- **Aplicação AgentTikTok:** conservar SRT antes de burn-in e testar áreas seguras/captions legíveis.

### 14 — Singapura 🇸🇬

- **Problema investigado:** social commerce, creator operations e pipelines curtos multi-plataforma.
- **Soluções/padrões encontrados:** material local de marketing enfatiza brief → roteiro → produção → postagem → métricas; exemplos de infraestrutura OSS global usam queue + storage + FFmpeg. Fontes locais de alta qualidade específicas de engenharia foram escassas.
- **Fontes/projetos:** [Creator toolkit guide (SG)](https://agentsetupsg.com/ai-tools-content-creators-influencers-singapore-2026/) (guia de produto, não benchmark); [TikTok Content Posting guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines) (**OFFICIAL**).
- **Falhas comuns:** “postar em várias redes” abstrai permissões/capacidades diferentes; nenhuma métrica fica observável automaticamente se o app não tiver scope e API.
- **Ideias úteis:** adaptar metadados e canal por platform adapter; analytics sempre com fonte/data.
- **Não usar:** presumir que um provider comercial conferiu scopes/consentimento do nosso app.
- **Aplicação AgentTikTok:** manter adapter de entrega isolado e identidade/observação como campos independentes.

### 15 — Rússia 🇷🇺

- **Problema investigado:** usar comunidade OSS para engenharia de vídeo, estados/retries/Android, sem depender de representatividade de TikTok regional.
- **Soluções/padrões encontrados:** documentação de automação e Android em russo reforça execução durável/WorkManager, retry de tarefas idempotentes e fila ACK; exemplos locais de agente de edição enviam resultado por canal de controle sem mover render para o celular.
- **Fontes/projetos:** [Android WorkManager](https://developer.android.com/develop/background-work/background-tasks/persistent) (**OFFICIAL**, documento base; disponível multilíngue); [square/workflow](https://github.com/square/workflow) (**OSS/STABLE**, estado de UI dirigido por máquina de estados); [FFmpeg](https://ffmpeg.org/documentation.html) (**OSS/STABLE**).
- **Falhas comuns:** retentar evento não idempotente, confundir fila de jobs com stream de eventos, manter processo FFmpeg filho após cancelamento.
- **Ideias úteis:** ACK explícito, estados terminais, eventos de progresso, retry apenas em operações recuperáveis, kill switch verificado no checkpoint.
- **Não usar:** considerar bloqueio geográfico ou dados TikTok locais como representativos do produto internacional.
- **Aplicação AgentTikTok:** conservar worker/lease/idempotency e o mecanismo de cancelamento por checkpoint já existente.

## B — seis rodadas independentes de GitHub

### 01 — English

Vocabulário usado: durable/agent workflow, short-form video factory, queue worker, uploader, TikTok Content Posting API, Playwright, idempotency, approval gate.

- **OFFICIAL:** [`tiktok/tiktok-opensdk-android`](https://github.com/tiktok/tiktok-opensdk-android), documentação oficial exportada nos repos não-oficiais e APIs oficiais consultadas no site TikTok.
- **OSS/STABLE:** [FFmpeg](https://github.com/FFmpeg/FFmpeg), [Android WorkManager sample](https://github.com/android/codelab-android-workmanager).
- **OSS/EXPERIMENTAL:** [GabrielLaxy/TikTokAIVideoGenerator](https://github.com/GabrielLaxy/TikTokAIVideoGenerator), [gyoridavid/short-video-maker](https://github.com/gyoridavid/short-video-maker), [OpenMontage](https://github.com/fivetaku/openmontage).
- **OFFICIAL API reference/integration:** [psyv27/tiktok-publisher](https://github.com/psyv27/tiktok-publisher); API is official, repo client is not endorsement/audit proof.
- **UNOFFICIAL/BROWSER AUTOMATION:** [wkaisertexas/tiktok-uploader](https://github.com/wkaisertexas/tiktok-uploader), [YanivGabay/tiktok-uploader](https://github.com/YanivGabay/tiktok-uploader), [jefftko/PostFlow](https://github.com/jefftko/PostFlow).
- **REVERSE ENGINEERED / UNSAFE/BYPASS:** [makiisthenes/TiktokAutoUploader](https://github.com/makiisthenes/TiktokAutoUploader) describes cookies and private request/signature methods; excluded from production.
- **Issue/failure evidence:** [Playwright publish error #238](https://github.com/wkaisertexas/tiktok-uploader/issues/238), [API scope failure in Postiz #1773](https://github.com/gitroomhq/postiz-app/issues/1773).
- **Useful extraction:** pipeline stage records, explicit status, retry & draft distinction. Browser selectors, session state, and stealth are not adopted.

### 02 — Português

Vocabulário usado: vídeo curto, corte/recorte, roteiro, legenda queimada/SRT, fila de tarefas, pipeline, publicação assistida, retomar execução, idempotência.

- Achados em PT-BR: [MoneyPrinterTurbo article/repo](https://github.com/harry0703/MoneyPrinterTurbo) (pipeline roteiro/voz/assets/legenda/FFmpeg, **OSS/EXPERIMENTAL**); [short-form-video-generator](https://github.com/CosmoJelly/short-form-video-generator) (local TTS/Whisper/FFmpeg, **OSS/EXPERIMENTAL**); [Short-Form-Video-Automation](https://github.com/TheSuperDenis/Short-Form-Video-Automation) marca publicação TikTok como manual (repo source available, não OSI OSS).
- **OFFICIAL:** [TikTok Research API PT-BR](https://developers.tiktok.com/pt-BR/products/research-api) limita elegibilidade e não é fonte comercial genérica.
- **BROWSER AUTOMATION/REVERSE ENGINEERED:** repositórios de uploader aparecem com Selenium/Playwright, cookie e UI; nenhum escolhido.
- **Falhas/extração:** gerar MP4 não é publicar; assets licenciados e áudio são dependências separadas; ícone de fila não prova job remoto.
- **Aplicação:** manter cópia local e resultado persistido; labels da UI em português com estados reais.

### 03 — 中文

Vocabulário usado: 短视频工厂、任务队列、断点续传、状态流转、重试、幂等、智能剪辑、抖音发布、审核箱.

- **OSS/EXPERIMENTAL:** [short-video-factory](https://github.com/lppmql/short-video-factory) (Celery/Redis, content-pool lifecycle); [MovieFlow](https://github.com/wordflowlab/movieflow) (specification, progressive validation, resumability); [Future-Of-Video](https://github.com/ZhengJiandan/Future-Of-Video) (asset/storyboard/render workflow).
- **OFFICIAL vs platform-specific:** repos for Douyin are not TikTok International API implementations. Official TikTok international Content Posting docs remain the authority for that API.
- **BROWSER AUTOMATION:** [PostFlow](https://github.com/jefftko/PostFlow), [social-auto-upload](https://github.com/dreammis/social-auto-upload). Issues demonstrate QR/login state and UI/selector drift.
- **REVERSE ENGINEERED/UNSAFE/BYPASS:** [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) documents private signatures/cookies; no code used.
- **Useful extraction:** producer/worker separation, unique job key, `NEED_REVIEW`, intermediate artifact retention, per-stage retries. Do not propagate Douyin private API assumptions.

### 04 — Русский

Vocabulário usado: конвейер коротких видео, очередь задач, идемпотентность, повторная попытка, долговечный workflow, состояние публикации, ручное подтверждение.

- **OSS/STABLE:** [square/workflow](https://github.com/square/workflow) compõe máquina de estados e UI unidirecional; Android/FFmpeg upstream como referência técnica.
- **OSS/EXPERIMENTAL:** repositórios open source de geração enumerados na rodada English, reavaliados com termos russos; não foi encontrada prova robusta de API/TikTok regional que mude o desenho.
- **BROWSER AUTOMATION:** uploaders de browser reusam sessão e dependem de UI.
- **REVERSE ENGINEERED/UNSAFE/BYPASS:** projetos que mascaram TLS/fingerprint ou constroem assinatura privada foram identificados e excluídos.
- **Falhas/extração:** retries duplicam efeitos sem idempotency; credenciais aparecem em arquivos de configuração/log se não houver redaction.
- **Aplicação:** aproveitar máquina de estados unidirecional no control plane; credenciais ficam server-side; nenhum comportamento de evasão.

### 05 — 日本語

Vocabulário usado: ショート動画生成、動画パイプライン、字幕焼き込み、投稿キュー、再試行、冪等性、人間承認、TikTok 投稿 API.

- **OSS/EXPERIMENTAL:** [MoneyPrinterTurbo README-ja](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/README-ja.md); [OpenMontage](https://github.com/fivetaku/openmontage) (pipeline YAML e approval points); [mcp-video](https://github.com/eg-ethan/mcp-video) (ferramentas de vídeo estruturadas).
- **OFFICIAL:** TikTok OpenSDK Android e docs internacionais; docs japonesas de workflow WorkManager disponíveis.
- **Falhas/extração:** repo traduzido não prova origem/uso japonês; endpoint e guideline têm versão global; imagem animada ainda pode parecer slideshow se não houver corte/variedade de cena.
- **Não usar:** automação de sessão disfarçada como SDK.
- **Aplicação:** plano de cena por beats, edição legível, manifesto reproduzível e status humano explícito.

### 06 — Español

Vocabulário usado: generación de vídeo corto, cola de trabajos, reintento, idempotencia, revisión humana, borrador/inbox, publicación asistida, render FFmpeg.

- **OSS/EXPERIMENTAL:** [tutorial-pipeline-reels](https://github.com/Drignacioalcala/tutorial-pipeline-reels), [ai-content-pipeline](https://github.com/roccopaz/ai-content-pipeline), [mcp-video](https://github.com/eg-ethan/mcp-video).
- **OSS/STABLE:** FFmpeg + subtitle/timecode workflow; Android WorkManager official docs.
- **UNOFFICIAL/BROWSER AUTOMATION:** [PostFlow](https://github.com/jefftko/PostFlow); [TikTok uploader issue](https://github.com/wkaisertexas/tiktok-uploader/issues/238).
- **Falhas/extração:** um tutorial de uso diário e uma issue de falha servem como prova do padrão/problema, não como benchmark de confiabilidade.
- **Aplicação:** inbox de origem, transcrição/seleção auditáveis, revisão pré-publicação, e ledger de status.

## C — síntese mundial

### WORLD FINDINGS → GITHUB EVIDENCE → SELECTED PATTERN → AGENTTIKTOK

| Achado repetido | Evidência | Padrão selecionado | Aplicação |
| --- | --- | --- | --- |
| Sistemas confiáveis dividem a geração em tarefas persistidas e recuperáveis | WorkManager, MovieFlow, Celery/Redis, OpenMontage, `growth_jobs` | Máquina de estados durável, leases, chave de idempotência, retry por estágio | Manter worker/ledger existente; nada de scheduler novo nesta etapa sem ciclo observado e gates |
| Render de qualidade é timeline, cenas, áudio, captions e QA, não “arquivo existe” | FFmpeg, Remotion, MoneyPrinterTurbo, YTTT, OpenMontage | Um plano de cenas como entrada comum; SRT/manifest/hash como saída validável | Preservar render V2; SRT e evidência no armazenamento; provenance fica no manifest/UI |
| Descoberta é específica à fonte e ao território | TikTok Creative Center/Next, Research API eligibility, Google Trends RSS | Cada item leva source, geography, collected_at; unknown nunca é imputado | Continuar BR Google search signal como `BR_SIGNAL`; adicionar feeds só com acesso/lícita previsível e rotulagem fiel |
| TikTok “upload” e “post” não são sinônimos | Official API scopes/upload/direct-post e estados | Separar render, handoff, inbox/draft e publicação verificada; nunca contar intent como delivery confirmada | Share Kit/Android intent continua revisão humana; API não selecionada para uso private-only |
| Bypass técnico compra fragilidade e risco de conta | Playwright issues, cookie uploader READMEs, repositórios reverse engineered | Estudar somente filas/retries/estados; nunca sessão/cookie/stealth/endpoint privado | Nenhum caminho browser automation em produção |
| Android deve ser control plane para tarefas duráveis, não renderizador de geração pesada em background | Android docs, mobile clipper examples | UI consulta fonte do servidor; progresso, cancelamento e resultado explícitos | Manter APK simples; adotar WorkManager apenas se e quando houver tarefa offline/diferida no telefone |
| Aprendizado só existe se mudar uma hipótese após observação ligada | YTTT review flow, clip ledgers, existing growth learning linkage | Experiment → source evidence → observation → lesson → nextMutation | Manter repetição desligada até evento/observação real e dedupe |

### Comparação dos candidatos

- **Confiabilidade:** official API > intent/Share Kit para handoff formal > browser automation. API ainda exige gate e consentimento; intent é simples, mas não fornece estado de publicação.
- **Segurança:** OAuth oficial/token server-side > intent com `FileProvider` > browser com sessão persistida > assinatura privada/cookies. Só os dois primeiros são aceitáveis.
- **Manutenção:** FFmpeg/WorkManager documentados e nossos contratos são preferíveis a selectors de Creator Studio ou assinatura web privada.
- **Custo/complexidade:** render local por FFmpeg e assets vetoriais é barato, reprodutível; vídeo generativo remoto é caro e variável; não adicionar serviço pago antes de provar necessidade.
- **Compatibilidade Android:** APK inicia share intent e apresenta histórico; não mantém fila infinita, browser bot ou render caro em background.
- **Compatibilidade TikTok:** APIs oficiais obedecem scopes e gates. A diretriz atual diz cliente não auditado fica em `SELF_ONLY`; descreve que o API Client não deve ser apenas para uso interno. O projeto do proprietário é uso próprio e privado, então Content Posting API não é selecionada como atalho.

## Button inventory → contracts → implementation

### Inventário auditado (GrowthWorkspace/GrowthStudio)

| Ação visível | Efeito real | Resultado verificável | Contrato/falha observada |
| --- | --- | --- | --- |
| Navegação Início/Experimentos/Mídia/Analytics/Ferramentas | muda aba local | `aria-current` e tela escolhida | nenhuma mutação remota |
| INICIAR AGENTE | POST control `START` | `RUNNING` e ciclo inicial com descoberta + jobs duráveis | bloqueia novo run se já houver experimento; não há scheduler/repeat |
| ABRIR VÍDEO PRONTO | GET `/v1/growth/creatives/{id}/video` | MP4 renderizado e hash no backend | renderiza novamente ao abrir; o artefato binário não é armazenamento durável hoje |
| PAUSAR | POST `PAUSE` | servidor `PAUSED`, bloqueia claims e checkpoints | retomar só a fila já existente |
| PARADA DE EMERGÊNCIA | confirmação, POST `EMERGENCY_STOP` | `STOPPED`, jobs abertos bloqueados e cancelamento cooperativo | latch sem reset implementado; sem scheduler ativo |
| Enviar para revisão no TikTok | Android `ACTION_SEND`/Web Share | início de intent/chooser | mostra intent direcionado vs seletor aberto; nenhum dos estados confirma importação/publicação |
| Baixar MP4 | download local | arquivo exportado | não envia nem publica |
| Renderizar MP4 manual | POST `/v1/creator-video` com foto/texto do operador | MP4 manual local | `MANUAL`, não caminho autônomo |
| Desconectar conta | chama desconexão de identidade | revogação local/backend | não deve ser confundido com delete de vídeos |

### Contratos selecionados

1. **Discovery/run:** um clique opera um run; resposta e erro devem preservar source/território/dedupe. Se houver duplicate, revelar que o criativo reutilizou evidência anterior.
2. **Control:** toda mutação espera confirmação do backend antes de exibir novo modo. STOP cancela por checkpoint e bloqueia jobs não iniciados; UI não promete cancelar tarefa externa que não controla.
3. **Share/handoff:** `TikTok intent started` prova somente abertura direcionada ao app. `Chooser opened` prova só que a folha de compartilhamento apareceu. Nenhum dos dois prova importação, caption, privacidade ou publicação. Reportar estados distintamente.
4. **Download/manual render:** distinguir arquivo local de criativo autônomo; tratar mídia como artefato, não como post.
5. **Publication:** só mostrar PUBLISHED após status API ou evidência externa registrada. Nunca inferir a partir de `Promise` resolvida por share sheet.

### Implementação selecionada

- Corrigir o contrato do botão de share no Android, navegador e Manual Studio para mostrar “intent TikTok iniciado” versus “seletor de compartilhamento aberto” e deixar publicação UNKNOWN.
- Remover do render a faixa persistente “SINAL: GOOGLE TRENDS BR · TIKTOK: UNKNOWN”; proveniência fica no manifesto e na tela de prévia. TikTok exige não colocar marca/logo promocional indesejada em conteúdo API-posted e esta tarja também enfraquece a peça criativa.
- Não alterar Login Kit, scopes, API de publicação, scheduler, fontes nem arquitetura de dados.

## Fontes primárias consultadas

- [TikTok Direct Post, atualizado 24 ago. 2026](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post) — `video.publish`, creator info, consentimento, upload e restrição de cliente não auditado.
- [TikTok Content Sharing Guidelines, atualizado 4 ago. 2026](https://developers.tiktok.com/docs/en/content-sharing-guidelines) — limite `SELF_ONLY` para não auditado; cap; intended audience; UX, preview e consentimento.
- [TikTok Research API PT-BR](https://developers.tiktok.com/pt-BR/products/research-api) — elegibilidade de pesquisa no Brasil; não é API de tendências para uso comercial pessoal.
- [Android WorkManager: requests, constraints and retry](https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started/define-work) — execução condicionada, retries/backoff e observabilidade/cancelamento.
- [FFmpeg documentation](https://ffmpeg.org/documentation.html) — pipeline de mídia/referência técnica.
