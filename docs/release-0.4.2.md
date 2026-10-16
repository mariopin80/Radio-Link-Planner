Radio Link Planner 0.4.2 para Windows x64.

- Cálculo P.1812 otimizado com reduções NumPy e fatiamento de arrays, mantendo as equações, a grade independente por célula e os perfis a 30 m.
- Terreno preparado uma única vez e acessado por arquivos mapeados, compartilháveis entre processos pelo sistema operacional. Isso reduz leituras e organização repetida sem criar uma cópia integral de cada tile em cada processo.
- Perda de propagação salva separadamente da margem. Ao mudar potência, ganho, perdas de cabo ou sensibilidade na mesma pasta de resultados, a perda válida é reaproveitada. Mudanças de frequência, alturas, coordenadas, polarização, percentual de tempo, raio, resolução ou dados científicos invalidam esse reaproveitamento.
- Contornos de 0, +3, +6 e +12 dB mais finos e transparentes, com rótulos mais espaçados no mapa interativo. O mapa técnico e o PDF também recebem contornos mais leves.
- Novo ícone de antena, ondas de rádio e relevo aplicado à janela, executável, atalhos e instalador.
- Cancelamento e retomada preservam a grade de perda em precisão dupla. Checkpoints antigos da versão 0.4.1 permanecem separados e não são misturados aos novos.

Inclui o instalador `RadioLinkPlanner-0.4.2-Windows-x64-Setup.exe`, o pacote portátil `RadioLinkPlanner-0.4.2-Windows-x64.zip` e `SHA256SUMS.txt`, além do código-fonte disponibilizado pelo GitHub.

A instalação usa a mesma identidade da versão anterior para permitir atualização. Projetos, resultados e os caches existentes permanecem no perfil do usuário. Os produtos digitais integrais da ITU continuam sendo obtidos diretamente da ITU para uso local.
