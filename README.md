# Radio Link Planner 0.5.1

Protótipo científico local para análise de enlaces terrestres de
radioamadorismo em VHF e UHF. O programa analisa enlaces ponto a ponto e
produz mapas de cobertura por grade métrica direta, além de calcular a
geometria, comparar modelos de propagação, aplicar Monte Carlo às incertezas
e gerar relatórios rastreáveis.

Esta versão reúne o **motor científico de linha de comando** e um MVP desktop
com dois módulos: **Enlace ponto a ponto** e **Mapa de cobertura**. Ela não
depende de servidor e não exige Python no computador do usuário. O seletor
cartográfico abre em uma janela nativa do aplicativo e usa temporariamente uma
página local somente em `127.0.0.1`; ela é encerrada assim que as coordenadas
são confirmadas e não recebe conexões da rede externa. Se o componente nativo
não estiver disponível, o navegador continua funcionando como alternativa.

## O que já funciona

- perfil de terreno Copernicus GLO-30 ou CSV importado;
- obtenção automática e cache local dos blocos Copernicus necessários;
- editor visual dos dois terminais e dos parâmetros principais do enlace;
- formulários responsivos, com tamanho inicial ampliado e rolagem vertical;
- seleção de localidades por coordenadas ou clique no mapa;
- projetos de enlace e cobertura com Novo, Abrir e Salvar;
- mapa interativo MapLibre com o percurso entre os terminais;
- cobertura P.1812 com raios de 50, 100, 200, 300, 400 ou 500 km;
- resolução rápida, recomendada, detalhada ou personalizada;
- uma execução independente da P.1812 para cada centro de célula a partir
  de 250 m, sem interpolação de propagação;
- perfis de terreno amostrados a 30 m, independentemente da resolução visual;
- previsão de tempo e memória antes da execução;
- progresso percentual, etapa, células concluídas e tempo restante;
- cancelamento e retomada automática dos blocos já concluídos;
- mapa de calor com escala de margem;
- contornos de 0, +3, +6 e +12 dB;
- contornos mais finos e transparentes, com rótulos espaçados no mapa;
- vetorização da P.1812 e terreno preparado em arquivos mapeados compartilháveis;
- reaproveitamento da perda ao ajustar potência, ganhos, cabos e sensibilidade;
- ícone próprio no executável, janela, atalhos e instalador;
- interface, mapas e relatórios em cinco idiomas;
- preferência de idioma persistente e seletor com bandeiras;
- aba Sobre com identificação e contato do desenvolvedor;
- curvatura terrestre com fator k configurável;
- primeira zona de Fresnel e obstruções críticas;
- ITM 1.3 oficial da NTIA em modo ponto a ponto;
- ITU-R P.1812-8;
- ITU-R P.2001-6, inclusive em VHF;
- orçamento bidirecional do enlace;
- curvas temporais de ITM e P.2001;
- Monte Carlo reproduzível sem duplicar a variabilidade atmosférica;
- limiares editáveis para FM, SSB, CW, APRS e LoRa;
- classificação, confiança e recomendações;
- JSON, Markdown, HTML, PDF e gráficos técnicos.

## Instalação para desenvolvimento

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev,plots,geo,models,desktop]"
.venv/bin/python scripts/build_itm.py
.venv/bin/python scripts/bootstrap_itu_data.py
```

No Windows, ative o ambiente com `.venv\Scripts\activate` e use
`python` no lugar de `.venv/bin/python`.

Os mapas digitais integrais da ITU não são incluídos neste repositório. O
script `bootstrap_itu_data.py` baixa os componentes diretamente da ITU para a
instalação local do usuário.

## Executar o caso de referência

```bash
radio-link analyze examples/morro_jacu_palmira.json \
  --output results/morro_jacu_palmira
```

Ou, sem instalar o comando:

```bash
PYTHONPATH=src python -m radiolink analyze \
  examples/morro_jacu_palmira.json \
  --output results/morro_jacu_palmira
```

## MVP desktop para Windows

O workflow **Windows release** produz dois formatos:

- `RadioLinkPlanner-0.5.1-Windows-x64-Setup.exe`: instalador recomendado;
- `RadioLinkPlanner-0.5.1-Windows-x64.zip`: pacote portátil para testes.

A versão 0.5.1 é uma pré-versão para validação antes da 1.0. A tela inicial
oferece português, inglês, espanhol, francês e alemão pelas bandeiras no topo,
ao lado de **Sobre**. O idioma escolhido é lembrado nas próximas aberturas e se aplica
aos formulários, mensagens, mapas, gráficos, resumos e PDFs. O instalador
oferece os mesmos cinco idiomas.

A aba **Sobre**, disponível nos módulos e pela tela inicial, mostra a versão,
mês/ano de lançamento, Mario Pin, PU2PTU e `mariopin@gmail.com`.

O tempo restante aparece uma única vez junto à barra de progresso. Os ícones
próprios dos atalhos e a atualização sobre a versão 0.5 são verificados na
construção do instalador. Projetos de cobertura novos armazenam opções
independentes do idioma (formato 1.1); a leitura dos projetos 1.0 permanece
compatível.

A previsão de duração considera o motor otimizado e o histórico compatível
da versão 0.4.2. A interface distingue uma estimativa inicial aproximada de
uma previsão pelo histórico deste computador. O intervalo se refere ao
cálculo e à geração dos mapas; downloads pendentes de terreno são indicados
à parte, pois dependem da conexão. Durante a execução, o tempo restante é
atualizado pelo trabalho efetivamente processado, considerando o tamanho dos
perfis de terreno.

O instalador cria a pasta `Program Files\Radio Link Planner`, atalhos no menu
Iniciar, um atalho opcional na área de trabalho e o desinstalador. Não é
necessário instalar Python. Resultados permanecem no perfil do usuário, em
`Radio Link Planner\Resultados`. O cache de terreno fica em
`%LOCALAPPDATA%\RadioLinkPlanner\Copernicus-GLO-30`, e os produtos digitais
da P.1812/P.2001 ficam em `%LOCALAPPDATA%\RadioLinkPlanner\ITU-R`; a
desinstalação não apaga esses dados.

Os arquivos aprovados ficam disponíveis na seção
[Releases](https://github.com/mariopin80/radio-link-planner/releases) do
repositório privado. A Release também inclui `SHA256SUMS.txt` para conferir a
integridade dos downloads.

Na primeira análise, o aplicativo precisa de internet para obter os produtos
digitais integrais diretamente da ITU e os blocos Copernicus GLO-30 do
percurso. Eles não são redistribuídos no ZIP. Os dados ficam em cache e as
análises seguintes dos mesmos locais podem ser repetidas offline. A camada
cartográfica OpenStreetMap requer internet para aparecer, mas não participa de
nenhum cálculo.

Os relatórios cartográficos devem ser abertos pelo botão **Mapa e relatório**
do aplicativo. O programa os disponibiliza temporariamente somente em
`127.0.0.1`, com uma URL aleatória, para que o navegador carregue corretamente
o mapa-base, o heatmap e os contornos sem expor os arquivos à rede externa.

O MVP permite:

- executar por duplo clique, sem terminal;
- escolher entre enlace ponto a ponto e mapa de cobertura na abertura;
- identificar os dois módulos por ilustrações próprias na tela inicial;
- analisar o caso real Morro do Jacu–Palmira já incluído;
- criar um enlace por coordenadas, frequência, modo, polarização e meta;
- escolher os locais digitando as coordenadas ou clicando no mapa;
- configurar altura, ganho, cabo, potência e sensibilidade de cada terminal;
- criar, salvar e abrir projetos de enlace ou cobertura;
- gerar automaticamente um pacote reproduzível com `project.json` e
  `terrain_profile.csv`;
- escolher o número de execuções Monte Carlo;
- gerar e abrir mapa, relatório HTML, relatório PDF e gráficos técnicos.

### Criar um mapa de cobertura

1. Na abertura, escolha **Mapa de cobertura**.
2. Informe a estação transmissora por coordenadas ou clique em
   **Escolher no mapa**.
3. Configure frequência, polarização, altura, ganho, perdas, potência e o
   receptor de referência.
4. Escolha o raio e a resolução **Rápida**, **Recomendada**, **Detalhada** ou
   **Personalizada**. A interface mostra a grade, as células, o tempo e a
   memória previstos.
5. Confirme o aviso quando a previsão ultrapassar 10 minutos e clique em
   **Calcular cobertura**.
6. Acompanhe percentual, etapa, células concluídas e tempo restante. O botão
   **Cancelar** preserva os blocos prontos; repetir os mesmos parâmetros e a
   mesma pasta retoma a execução.
7. Abra o mapa interativo ao concluir.

Depois da primeira cobertura na versão 0.4.2, ajustes de potência, ganho,
perdas de linha ou sensibilidade na mesma pasta de resultados reutilizam a
perda calculada. O mapa, os contornos e os relatórios são atualizados para o
novo orçamento do enlace. A interface informa quando essa reutilização está
disponível. Mudanças dos parâmetros físicos de propagação ou dos dados
científicos exigem novo cálculo. O programa verifica a integridade da grade
de perda antes de reutilizá-la.

Os pixels preparados ficam na subpasta `prepared` do cache Copernicus. São
arquivos mapeados somente para leitura pelos processos; o sistema operacional
compartilha e pode recuperar essas páginas de memória. Essa preparação usa
espaço adicional em disco, sem alterar a amostragem de 30 m. Se o cache não
puder ser gravado, o programa usa a leitura de blocos já existente.

A cobertura usa a ITU-R P.1812-8 em um percentual de tempo entre 1 e 50%. O
raster é uma grade azimutal equidistante centrada no transmissor. Cada célula
a partir de 250 m recebe uma execução independente da P.1812 com seu próprio
perfil Copernicus GLO-30. Abaixo de 250 m, fora do escopo de distância
declarado pela recomendação, é usada perda em espaço livre e essa exceção é
registrada separadamente. A imagem pode ser reamostrada apenas para exibição;
o motor não interpola perda entre células.

Resoluções recomendadas:

| Raio | Rápida | Recomendada | Detalhada |
|---:|---:|---:|---:|
| 50 km | 200 m | 100 m | 50 m |
| 100 km | 400 m | 200 m | 100 m |
| 200 km | 800 m | 400 m | 200 m |
| 300 km | 1.200 m | 600 m | 300 m |
| 400 km | 1.600 m | 800 m | 400 m |
| 500 km | 2.000 m | 1.000 m | 500 m |

A grade recomendada mantém aproximadamente 785 mil células dentro do círculo.
O custo de cada célula ainda cresce com o comprimento do perfil, portanto
raios grandes podem levar horas mesmo com a mesma quantidade de células. A
estimativa inicial é recalibrada com o desempenho medido no computador.

No pacote portátil, todos os arquivos extraídos devem permanecer juntos. Para
uso normal, prefira o instalador.

### Criar o primeiro enlace próprio

1. Abra `RadioLinkPlanner.exe`, escolha **Enlace ponto a ponto** e clique em
   **Novo projeto**.
2. Preencha as coordenadas e os dados de rádio dos terminais A e B.
3. Na aba **Análise e resultados**, escolha a pasta de saída e o número de
   execuções Monte Carlo.
4. Clique em **Obter terreno e analisar**.
5. Use **Mapa e relatório** para ver o percurso, o perfil e o parecer completo.

A interface 0.4 é deliberadamente limitada a 30–3000 MHz e percursos de
3–1000 km. Esses limites correspondem ao foco VHF/UHF desta etapa; o motor
científico mantém faixas mais amplas para evolução futura.

O perfil automático ainda assume zona terrestre interior ao longo de todo o
percurso e não contém vegetação ou edificações. O relatório declara essa
limitação; trajetos costeiros ou sobre água precisam de revisão do
`zone_code`.

Para executar a interface durante o desenvolvimento:

```bash
radio-link-desktop
```

Arquivos gerados:

- `result.json`: resultados completos e rastreáveis;
- `summary.md`: parecer técnico;
- `report.html`: relatório visual local;
- `relatorio_enlace.pdf`: relatório técnico portátil e imprimível;
- `profile.png`: relevo, raio direto, curvatura e Fresnel;
- `monte_carlo.png`: comparação probabilística dos modelos.

Para a cobertura:

- `coverage_project.json`: parâmetros usados no cálculo;
- `coverage_margin_db.npy`: grade direta final de margem;
- `coverage_loss_db.npy`: perda física por célula em precisão dupla;
- `coverage_propagation.json`: identidade e integridade da perda reutilizável;
- `coverage_metadata.json`: motor, versão, células, perfis, tempos,
  paralelismo e hipóteses científicas;
- `coverage_overlay.png`: camada transparente para o mapa;
- `coverage_contours.geojson`: linhas de 0, +3, +6 e +12 dB;
- `coverage_heatmap.png`: mapa técnico com escala;
- `coverage_report.html`: mapa interativo e rastreabilidade;
- `relatorio_cobertura.pdf`: síntese técnica portátil e imprimível.

## Demonstração reproduzível

O diretório [`demo-output`](demo-output) contém a saída completa gerada pelo
caso Morro do Jacu–Palmira. Os números abaixo não são valores ilustrativos:
foram produzidos pelos três modelos durante a validação da versão 0.1.

![Perfil técnico Morro do Jacu–Palmira](demo-output/profile.png)

![Monte Carlo do caso de referência](demo-output/monte_carlo.png)

## Testes

```bash
pytest
```

Os testes geométricos e de orçamento não exigem internet. Os ensaios completos
dos três modelos são executados quando os componentes opcionais foram
instalados.

## Estado científico da 0.4

O programa separa três perguntas que calculadoras simples costumam misturar:

1. **qual é a perda mediana?**
2. **qual é a perda em determinado percentual de tempo?**
3. **qual é a chance de o equipamento real superar o limiar, considerando
   incertezas?**

ITM e P.2001 fornecem curvas temporais completas. A P.1812 é usada como
comparação independente até 50% do tempo e não é extrapolada para
disponibilidades superiores.

Consulte [docs/scientific-scope.md](docs/scientific-scope.md) para limitações,
hipóteses e critérios de classificação.

