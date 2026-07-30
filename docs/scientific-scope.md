# Escopo científico da versão 0.3

## Aplicação declarada

Enlaces terrestres fixos, predominantemente entre 3 e 1.000 km, nas faixas de
VHF e UHF. A versão 0.3 não deve ser usada como modelo validado para enlaces
móveis urbanos, aeronáuticos, via satélite ou HF ionosférico.

## Modelos

### ITM 1.3 da NTIA

Executado em modo ponto a ponto com o perfil de terreno igualmente espaçado.
Os parâmetros de confiança e confiabilidade são preservados no resultado. O
mecanismo dominante e os valores intermediários são retornados pela biblioteca
oficial.

### ITU-R P.1812-8

Usada como previsão dependente do percurso para 30 MHz a 6 GHz. Como a
recomendação calcula percentuais de tempo de 1% a 50%, a versão 0.1 não
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

## Terreno automático da versão 0.3

O editor obtém elevações do Copernicus GLO-30 e mantém os blocos em cache
local. O perfil automático ainda atribui a classe de zona terrestre interior
ao percurso inteiro e não inclui vegetação ou edificações. Enlaces costeiros,
sobre mar ou sobre grandes corpos d'água exigem revisão manual da coluna
`zone_code` do perfil antes de um parecer definitivo.

## Cobertura adaptativa da versão 0.3

O módulo ponto-área usa a ITU-R P.1812-8 como modelo único. Uma primeira
passagem calcula perfis com separação de 10°. Pares de perfis são subdivididos
quando apresentam descontinuidade relevante de relevo, margem ou alcance com
margem positiva. Ao longo de cada radial, pontos intermediários também são
adicionados quando a margem não é linear, o terreno se afasta fortemente da
tendência local ou um contorno operacional é atravessado.

O raster final tem 50 m para raio de 50 km, 100 m para 100–200 km e 200 m para
300–500 km. Esses valores descrevem a grade interpolada, não a distância entre
todas as execuções independentes da P.1812. A saída registra ambos os números
para impedir que a resolução visual seja confundida com densidade física.

Os contornos operacionais são 0, +3, +6 e +12 dB. A cobertura ainda assume
zona terrestre interior, receptor uniforme e ausência de vegetação e
edificações. O método adaptativo precisa ser validado contra uma grade
cartesiana densa e medições de campo antes de qualquer afirmação geral de
superioridade.

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
