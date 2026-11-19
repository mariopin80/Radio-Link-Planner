# Radio Link Planner 0.6.1

Pré-lançamento para Windows x64 com correções e melhorias na criação de projetos.

- **Terreno de enlaces** — valida coordenadas dos extremos e distância do perfil antes de reutilizar dados de projetos anteriores. Um perfil incompatível é substituído automaticamente por um novo perfil Copernicus GLO-30. Corrige o erro de 89,656% observado ao salvar um enlace diferente do exemplo. #41
- **Novo Enlace** — o formulário passa a abrir com o nome *Novo Enlace*, sem coordenadas nem valores de equipamento definidos. O caso Morro do Jacu–Palmira continua disponível pela ação explícita de carregar exemplo. #40
- **Nova Cobertura** — os dados de transmissores, antenas e receptor começam vazios; permanecem como sugestões os parâmetros de análise (raio de 50 km, resolução Recomendada e 50% do tempo P.1812). #44
- **Resultados** — a pasta padrão acompanha o nome do enlace ou da cobertura, preservando destinos escolhidos manualmente e os resultados de execuções anteriores. #42
- **Segurança dos cálculos** — testes de regressão verificam a invalidação de caches e checkpoints incompatíveis e a reutilização das perdas físicas quando mudam apenas parâmetros do orçamento de enlace. #45

Os modelos científicos ITM, P.1812 e P.2001 não foram alterados.

## Downloads

- `RadioLinkPlanner-0.6.1-Windows-x64-Setup.exe` — instalador Windows
- `RadioLinkPlanner-0.6.1-Windows-x64.zip` — versão portátil
- `SHA256SUMS.txt` — hashes SHA-256 dos dois arquivos
