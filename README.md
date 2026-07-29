# Radio Link Planner 0.2

Protótipo científico local para análise de enlaces terrestres de
radioamadorismo em VHF e UHF. O programa calcula a geometria do percurso,
executa modelos de propagação independentes, aplica Monte Carlo às
incertezas e gera um relatório rastreável.

Esta versão reúne o **motor científico de linha de comando** e um MVP desktop
capaz de criar enlaces próprios. Ela não depende de servidor, não abre porta
local e não exige Python no computador do usuário.

## O que já funciona

- perfil de terreno Copernicus GLO-30 ou CSV importado;
- obtenção automática e cache local dos blocos Copernicus necessários;
- editor visual dos dois terminais e dos parâmetros principais do enlace;
- mapa interativo MapLibre com o percurso entre os terminais;
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
- JSON, Markdown, HTML e gráficos técnicos.

## Instalação para desenvolvimento

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev,plots,geo,models]"
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

O pacote portátil `RadioLinkPlanner-0.2-Windows-x64.zip` é produzido
automaticamente pelo workflow **Windows MVP**. Depois de descompactar, execute
`RadioLinkPlanner.exe`; não é necessário instalar Python.

O ZIP aprovado fica disponível na seção
[Releases](https://github.com/mariopin80/radio-link-planner/releases) do
repositório privado.

Na primeira análise, o aplicativo precisa de internet para obter os produtos
digitais integrais diretamente da ITU e os blocos Copernicus GLO-30 do
percurso. Eles não são redistribuídos no ZIP. Os dados ficam em cache e as
análises seguintes dos mesmos locais podem ser repetidas offline. A camada
cartográfica OpenStreetMap requer internet para aparecer, mas não participa de
nenhum cálculo.

O MVP permite:

- executar por duplo clique, sem terminal;
- analisar o caso real Morro do Jacu–Palmira já incluído;
- criar um enlace por coordenadas, frequência, modo, polarização e meta;
- configurar altura, ganho, cabo, potência e sensibilidade de cada terminal;
- abrir e editar outro projeto JSON;
- gerar automaticamente um pacote reproduzível com `project.json` e
  `terrain_profile.csv`;
- escolher o número de execuções Monte Carlo;
- gerar e abrir mapa, relatório HTML e gráficos técnicos.

O pacote é uma pasta portátil, não um instalador. Todos os arquivos extraídos
devem permanecer juntos e em uma pasta gravável pelo usuário.

### Criar o primeiro enlace próprio

1. Abra `RadioLinkPlanner.exe` e clique em **Novo enlace**.
2. Preencha as coordenadas e os dados de rádio dos terminais A e B.
3. Na aba **Análise e resultados**, escolha a pasta de saída e o número de
   execuções Monte Carlo.
4. Clique em **Obter terreno e analisar**.
5. Use **Mapa e relatório** para ver o percurso, o perfil e o parecer completo.

A interface 0.2 é deliberadamente limitada a 30–3000 MHz e percursos de
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
- `profile.png`: relevo, raio direto, curvatura e Fresnel;
- `monte_carlo.png`: comparação probabilística dos modelos.

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

## Estado científico da 0.2

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
