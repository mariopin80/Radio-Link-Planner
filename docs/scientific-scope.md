# Escopo científico da versão 0.4

## Aplicação declarada

Enlaces terrestres fixos, predominantemente entre 3 e 1.000 km, nas faixas de
VHF e UHF. A versão 0.4 não deve ser usada como modelo validado para enlaces
móveis urbanos, aeronáuticos, via satélite ou HF ionosférico.

## Modelos

### ITM 1.3 da NTIA

Executado em modo ponto a ponto com o perfil de terreno igualmente espaçado.
Os parâmetros de confiança e confiabilidade são preservados no resultado. O
mecanismo dominante e os valores intermediários são retornados pela biblioteca
oficial.

### ITU-R P.1812-8

Usada como previsão dependente do percurso para 30 MHz a 6 GHz. Como a
recomendação calcula percentuais de tempo de 1% a 50%, a versão 0.4 não
extrapola a P.1812 para disponibilidades superiores a 50%.

### ITU-R P.2001-6

Usada como modelo temporal de 30 MHz a 50 GHz. A implementação é confrontada
com os exemplos de validação oficiais, que incluem 30 MHz e 200 MHz. Seus
mapas digitais integrais são obtidos diretamente da ITU e não são
redistribuídos.

## Monte Carlo

As curvas temporais de ITM e P.2001 já contêm variabilidade de propagação.
Por isso, o Monte Carlo amostra essas curvas e, separadamente, as incertezas
de equipamento e instalação. Não é somada uma perda atmosférica aleatória
arbitrária.

As variáveis iniciais são:

- potência efetiva do transmissor;
- ganho efetivo de cada antena;
- perdas de linhas e conectores;
- apontamento;
- polarização;
- limiar efetivo do receptor.

Erros do DEM e alturas ainda não são perturbados no Monte Carlo atual. Eles
aparecem como limitações do parecer. Uma versão futura deverá usar erros
espacialmente correlacionados e reexecutar o modelo ou um metamodelo validado.

## Terreno automático da versão 0.4

O editor obtém elevações do Copernicus GLO-30 e mantém os blocos em cache
local. O perfil automático ainda atribui a classe de zona terrestre interior
ao percurso inteiro e não inclui vegetação ou edificações. Enlaces costeiros,
sobre mar ou sobre grandes corpos d'água exigem revisão manual da coluna
`zone_code` do perfil antes de um parecer definitivo.

## Cobertura por grade direta da versão 0.4

O módulo ponto-área usa a ITU-R P.1812-8 como modelo principal. A área é
representada em uma grade métrica de projeção azimutal equidistante, centrada
no transmissor. Para cada centro de célula situado a partir de 0,25 km:

1. é determinada a coordenada geográfica do receptor;
2. é extraído um perfil geodésico próprio do Copernicus GLO-30;
3. o terreno é amostrado nominalmente a 30 m, sem depender do tamanho da
   célula;
4. a P.1812 é executada para aquele percurso;
5. a margem é gravada diretamente na célula correspondente.

Não há interpolação de perda ao longo de radiais ou entre ângulos. O
heatmap pode sofrer reamostragem gráfica para caber no navegador, sem alterar
a grade científica salva em `coverage_margin_db.npy`.

A P.1812-8 declara aplicação para distâncias de aproximadamente 0,25 a
3.000 km. As células mais próximas que 0,25 km usam perda em espaço livre,
registrada separadamente em `short_range_free_space_cells`. Isso evita
apresentar como P.1812 um resultado fora do escopo declarado.

As resoluções de referência são:

| Raio | Rápida | Recomendada | Detalhada |
|---:|---:|---:|---:|
| 50 km | 200 m | 100 m | 50 m |
| 100 km | 400 m | 200 m | 100 m |
| 200 km | 800 m | 400 m | 200 m |
| 300 km | 1.200 m | 600 m | 300 m |
| 400 km | 1.600 m | 800 m | 400 m |
| 500 km | 2.000 m | 1.000 m | 500 m |

A resolução recomendada produz cerca de 785 mil células dentro do círculo.
Isso não implica tempo constante: um perfil de 500 km contém muito mais
amostras e custa mais que um perfil de 50 km. A interface estima duração e
memória, alerta acima de 10 minutos, usa processos paralelos e recalibra o
tempo restante conforme os blocos terminam.

Cada bloco concluído é salvo antes de ser marcado como pronto. Cancelamentos
e falhas preservam a grade parcial e o estado dos blocos; uma execução com os
mesmos parâmetros, motor e pasta retoma somente o trabalho restante.

Os contornos operacionais são 0, +3, +6 e +12 dB. A cobertura ainda assume
zona terrestre interior, receptor uniforme e ausência de vegetação e
edificações. A eliminação da interpolação radial resolve uma fonte de
suavização, mas não torna P.1812 e ITM equivalentes e não substitui validação
contra valores ponto a ponto, Radio Mobile e medições de campo.

## Critérios de classificação

- **robusto**: todos os modelos aplicáveis apresentam margem de pelo menos
  10 dB no ponto de projeto;
- **viável**: todos apresentam margem de pelo menos 3 dB;
- **marginal**: há divergência de sinal entre os modelos ou alguma margem fica
  entre -3 e 3 dB;
- **improvável**: todos apresentam margem negativa relevante.

A confiança é reduzida quando há forte divergência entre modelos, ausência de
clutter, ruído local não medido ou dados de terreno insuficientes.

## Limiares de modos

Quando não existe um limiar medido, o programa calcula:

`-174 dBm/Hz + 10 log10(BW) + NF + ruído externo + SNR requerida`

Esses perfis são editáveis e nunca substituem a especificação ou a medição do
rádio real.
