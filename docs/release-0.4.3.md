Radio Link Planner 0.4.3 para Windows x64.

- Corrige a associação dos ícones dos atalhos do menu Iniciar e da área de trabalho. O instalador passa a instalar o ícone aprovado em arquivo próprio e a apontar explicitamente cada atalho para ele. O nome do arquivo inclui a versão para não reutilizar a referência anterior durante a atualização.
- Recalibra a previsão de duração para o motor otimizado. Considera o trabalho fixo por célula e o comprimento dos perfis, em vez de superestimar o crescimento do custo com a distância.
- Mantém e aproveita o histórico compatível da versão 0.4.2, recalculando a velocidade com as contagens e o tempo efetivamente medidos no computador. A interface informa se a previsão usa histórico local ou valores iniciais aproximados.
- O tempo de download deixa de receber um acréscimo arbitrário por tile. A previsão identifica o cálculo e a geração dos mapas; blocos de terreno que ainda precisam ser baixados são informados à parte, pois sua duração depende da conexão.
- O tempo restante durante o cálculo passa a considerar as amostras de terreno processadas, incluindo a retomada de trabalhos parciais.

Mantém as otimizações da versão 0.4.2, os perfis a 30 m e o reaproveitamento da perda de propagação. O ajuste da previsão não altera a grade nem o modelo científico.

A validação Windows inclui instalação da versão 0.4.2, atualização para a 0.4.3, inspeção dos atalhos reais e decodificação do arquivo de ícone pelo Windows, além dos testes do aplicativo portátil, do aplicativo instalado e da desinstalação.

Inclui instalador, pacote portátil e `SHA256SUMS.txt`. É possível instalar sobre a versão 0.4.2.
