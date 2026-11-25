# PU2PTU - Radio Link Planner 0.6.3

Pré-lançamento para avaliação no Windows x64.

- A cobertura tenta novamente salvar o checkpoint quando o Windows bloqueia temporariamente o arquivo. Se o bloqueio persistir, a mensagem informa a pasta do checkpoint e como retomar os blocos salvos. #51
- Os relatórios de enlace esclarecem os critérios de concordância entre modelos e de Fresnel. A recomendação de equipamento considera as condições simuladas e o ruído do receptor. #52 #55 #56
- Os dois sentidos do enlace têm gráficos de Monte Carlo próprios. A meta anual aparece no painel de disponibilidade, e o sucesso condicional da P.1812 aparece no painel com seu percentil. #53 #54 #57
- Os PDFs de enlace passam a informar a versão do motor, o limiar de recepção e o número de simulações por modelo e sentido. A exportação incorpora as fontes do texto. #58 #59
- As cores e marcas da legenda de cobertura correspondem à escala do mapa. O PDF identifica a vista parcial e a área usada para calcular os percentuais. #60 #63
- O PDF de cobertura informa a hipótese de terra interior, a origem da margem máxima quando calculada em espaço livre, o modo RX, a versão do motor e o passo de amostragem do terreno. #61 #62 #64

## Downloads

- `RadioLinkPlanner-0.6.3-Windows-x64-Setup.exe` — instalador com aceite dos termos de avaliação no idioma selecionado
- `SHA256SUMS.txt` — hash SHA-256 do instalador

Relate problemas nas [issues do projeto](https://github.com/mariopin80/Radio-Link-Planner/issues).
