# Radio Link Planner 0.6.0

Pré-lançamento para Windows x64.

- **Tela inicial** — ilustrações de Enlace e Cobertura maiores, com dimensionamento proporcional à janela.
- **Interface** — ajuda dos ícones azuis na própria tela, sem bip. Janela de otimização de alturas com os estilos do aplicativo. #29 #30
- **Perfil e cobertura** — perfil e otimizador usam k = 4/3 e 60% da primeira zona de Fresnel. A cobertura mantém os mapas de margem e S estimado e gera os contornos na resolução da grade calculada. #28 #33
- **Enlace** — resultados do ITM com avisos aparecem no parecer. A interface indica quais modelos sustentam o parecer na meta e conserva os limiares do receptor por estação e modo. #31 #32
- **Monte Carlo** — os relatórios mostram o intervalo amostrado e a faixa de disponibilidade anual estimada quando as caudas não estão representadas. #34
- **Resultados** — cada execução concluída tem sua pasta em `runs/`. Falhas e cancelamentos preservam execuções anteriores, e a cobertura continua reaproveitando perdas e retomando cálculos interrompidos. #35

## Downloads

- `RadioLinkPlanner-0.6.0-Windows-x64-Setup.exe` — instalador
- `RadioLinkPlanner-0.6.0-Windows-x64.zip` — versão portátil
- `SHA256SUMS.txt` — hashes SHA-256
