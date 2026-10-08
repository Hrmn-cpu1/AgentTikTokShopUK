# AgencyOS Creative Studio — Agent #01 / estudo de confiabilidade
**Data local:** 2026-10-07 (America/Sao_Paulo) · **Autor operacional:** Nika (IA) · **Escopo:** PR #12, branch `feat/creative-studio-asmr-agent01`.

## Estado recuperado, preservado e auditado
- Repositório: Hrmn-cpu1/AgentTikTokShopUK. App existente permanece `main`; PR #12 em draft.
- Base reutilizada: Python + FFmpeg/ffprobe + `media_storage.hash_file`. `growth_worker`, `media_storage` e `delivery_gateway` existentes **não foram conectados ao novo renderer ASMR**.
- Render de ASMR na branch: 1–8 clipes locais autorizados, som ambiente externo autorizado, 6–60 s, export H.264/AAC vertical, sequência normalizada, stream-copy no merge, thumbnail, SHA-256 e manifesto de fontes.
- Gates existentes: direitos apenas **autodeclarados** com evidence ID, revisão editorial pendente, publicação bloqueada, draft local sem promoção durável.
- GitHub Actions do commit `033b73f`: Backend, Frontend, E2E, APK = SUCCESS; suíte de backend: 157 testes PASS, 1 aviso de depreciação de dependência. Isto prova apenas o estado daquele commit.
- Nenhuma mídia original, áudio ASMR real ou licença comercial da Ana Paula foi verificada. Nenhum post, deploy ou serviço pago foi solicitado.

## Fontes oficiais e aprendizados aplicados
1. **FFmpeg concat demuxer**: segmentos precisam ter codec, streams e time base compatíveis; divergência de duração pode produzir lacunas. Fonte: https://ffmpeg.org/ffmpeg-formats.html (concat) e https://github.com/FFmpeg/FFmpeg/blob/master/doc/demuxers.texi. A arquitetura codifica cada trecho para H.264/24fps/time base normalizada antes de `concat` e usa `-c copy` apenas depois.
2. **FFprobe -count_frames**: valida o número efetivamente decodificado, não apenas `nb_frames` de cabeçalho. Fonte: https://ffmpeg.org/ffprobe.html . Adicionada checagem obrigatória `decoded_frame_count` para corresponder à soma dos quadros da edição.
3. **EBU R128 e true peak**: `ebur128=peak=true` gera relatório de loudness integrado e true peak. Fonte: https://ffmpeg.org/ffmpeg-filters.html . Adicionadas medição read-only `integratedLufs` e `truePeakDbFS`; bloquear peak acima de -1 dBFS (relatório do true peak). Não equalizar/normalizar automaticamente ASMR.
4. **Processo sem shell**: Python `subprocess.run` com argv e timeout evita shell injection e libera recursos após timeout. Fonte: https://docs.python.org/3/library/subprocess.html . Já implementado em `_run`, com arquivos parciais removidos após falha ordinária.
5. **Meta e originalidade**: conteúdo original tem preferência nas recomendações; cortar/republicar vídeo de terceiros não cria licença. Fonte: https://about.fb.com/br/news/2024/04/ajudando-o-criador-de-conteudo-a-encontrar-novos-publicos/ . Não usar vídeos baixados de terceiros como se fossem atendimentos da Ana Paula.
6. **Projeto open source de referência**: https://github.com/gyoridavid/short-video-maker contém padrões de montagem e self-hosting, porém usa mais dependências/serviços e não é substituto direto de um editor ASMR fiel ao material original. Apenas ideias, sem copiar infraestrutura, mídia ou uploader.

## Riscos conhecidos e decisão por prioridade

| Prioridade | Falha potencial | Mitigação aplicada / em aberto | Gate |
|---|---|---|---|
| P0 | Conteúdo sem direito comercial, consentimento da pessoa filmada ou sem atribuição honesta | IDs de evidência e bloqueio de publicação; validação jurídica/editorial manual ainda necessária | RED até direitos verificados |
| P0 | Publicação automática sem revisão | renderer devolve `publication=BLOCKED`; sem upload/auto-post | GREEN no protótipo |
| P0 | Arquivo renderizado não corresponde ao plano | SHA-256 de fontes; edição por quadros; contagem decodificada e diferença A/V | Testes CI |
| P0 | Áudio alto/clipping ou A/V fora de sincronia | QA de true peak, pico por amostra e sincronismo | Testes CI + fones reais |
| P1 | Processo morre por SIGKILL / falta de espaço | `mkdir` exclusivo, cleanup em exceções; limpeza de órfãos, cgroup/limites reais e recuperação pós-kill ainda não implementadas | RED para processamento desassistido |
| P1 | Formatos móveis/VFR/rotação/codec exótico | trilha sequencial, fps fixo e uso de ffprobe; falta matriz extensa com vídeos reais heterogêneos | YELLOW |
| P1 | Reprodução em 1080×1920 em CPU limitada | export possível, sem benchmark de CPU, RAM, I/O e p95 no Railway | YELLOW |
| P1 | Artefato local perdido após reinício | media_storage durável existe no produto, mas ASMR não integra caminho de write/readback | RED para serviço autônomo |
| P1 | Falsos positivos de `blackdetect` em estética low-light | revisão manual; thresholds dependem do look; não alegar 100% precisão | YELLOW |
| P2 | Reels sem retenção/resultado real | brief, primeiros 0,8–2,5 s, gestures legíveis, áudio original, testes A/B e medição de contatos | RED até campanha real |
| P2 | Depreciação Starlette/httpx | um aviso registrado no backend; tratar em manutenção de dependências, sem upgrades às cegas | YELLOW |

## Protocolo de aceitação em vez de promessa impossível de 100%

**Release técnico mínimo**: PR tests green; sem exceções silenciosas; validação MP4 por decode completo/quadros; A/V <=250ms; áudio audível e true peak <= -1dBFS; SHA e manifesto verificados; recupera ou abandona sem falso `READY`; teste de interrupção/concorrência; teste de 1080p e perfis móveis; `NO_PAID_PROVIDERS`.

**Release comercial mínimo**: direitos, consentimento e serviço real comprovados; operador aprova corte/gestos/branding/som no celular; sem promessas médicas; um dono humano decide publicação; sucesso medido por métricas verificáveis de retenção e leads, não por viralização presumida.

**Release operacional mínimo**: integrar com RailwayVolumeMediaStore já existente, readback SHA antes de READY, quota, shutdown/restart e observabilidade; não alterar workers e app atuais antes destes testes.

## Plano priorizado da próxima etapa
1. Concluir CI do ajuste EBU R128 + frame count e corrigir falhas se existirem.
2. Criar fixtures de VFR/rotação, silêncio, áudio com pico alto, arquivo truncado, 8 clipes, paths Unicode e concorrência em um runner efêmero. Revisar falsos positivos, se houver.
3. Testar interrupção por SIGKILL, limpeza órfã e consumo real de memória/RAM/p95, sem fazer deploy.
4. Implementar **adaptador separado** de armazenamento durável (QA + hash lido após gravação) antes de qualquer API pública/Android.
5. Receber mídia original autorizada da Paula, inspecionar 1 Reel de ~15 s e fazer QA editorial de vídeo + áudio.
6. Apenas com aprovação do dono: merge/deploy/publicação, cada etapa explícita e rastreável.

## Decisões registradas
- Python permanece o motor; não reescrever em Java/CV sem vantagem mensurada.
- FFmpeg sem serviços pagos. Infra já existente pode ter cobrança de CPU/disco; não chamar toda computação de grátis.
- Teste técnico com imagens/som artificiais **não comprova** qualidade comercial.
- `main`, produção Railway, contas Instagram/TikTok, chaves e cobrança não serão alteradas nesta rodada.
