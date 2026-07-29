# Morro do Jacu – Palmira

Versão do motor: 0.1.0

## Geometria

- Distância: 180.192 km
- Pior bloqueio geométrico: 558.8 m a 40.9 km
- Raio máximo da primeira Fresnel: 304.1 m
- Fresnel de 60% obstruída em 90.2% do percurso

## Morro do Jacu → Palmira

**Parecer: marginal**
Confiança: baixa

### Comparação coerente em 50%

| Modelo | Perda (dB) |
|---|---:|
| ITM | 164.88 |
| P1812 | 171.24 |
| P2001 | 175.49 |

Dispersão entre modelos: **10.61 dB**.

### Ponto de projeto: 70%

| Modelo | Quantil de projeto | Perda (dB) | Potência (dBm) | Margem (dB) |
|---|---:|---:|---:|---:|
| ITM | 70.0% | 168.37 | -113.83 | 7.15 |
| P1812 | 50.0% | 171.24 | -116.70 | 4.28 |
| P2001 | 70.0% | 177.34 | -122.80 | -1.82 |

> A P.1812 é limitada a 1–50% do tempo. Seu valor na tabela é mediano e não representa a meta de 70%.

### Recomendações

- usar SSB quando isso for operacionalmente aceitável: aproximadamente +7.2 dB (modelo de ruído configurado para o receptor).
- aumentar o ganho da antena de Morro do Jacu para 9 dBi: aproximadamente +7.0 dB (ganho direto no orçamento do enlace).
- reduzir cada perda de linha para aproximadamente 0,5 dB: aproximadamente +2.0 dB (redução direta no orçamento do enlace).

### Incertezas declaradas

- vegetação e edificações não estão representadas.
- o ruído local do receptor ainda não foi medido.
- erros verticais do DEM não são amostrados no Monte Carlo 0.1.

## Palmira → Morro do Jacu

**Parecer: marginal**
Confiança: baixa

### Comparação coerente em 50%

| Modelo | Perda (dB) |
|---|---:|
| ITM | 164.88 |
| P1812 | 171.24 |
| P2001 | 175.49 |

Dispersão entre modelos: **10.61 dB**.

### Ponto de projeto: 70%

| Modelo | Quantil de projeto | Perda (dB) | Potência (dBm) | Margem (dB) |
|---|---:|---:|---:|---:|
| ITM | 70.0% | 168.37 | -113.83 | 7.15 |
| P1812 | 50.0% | 171.24 | -116.70 | 4.28 |
| P2001 | 70.0% | 177.34 | -122.80 | -1.82 |

> A P.1812 é limitada a 1–50% do tempo. Seu valor na tabela é mediano e não representa a meta de 70%.

### Recomendações

- usar SSB quando isso for operacionalmente aceitável: aproximadamente +7.2 dB (modelo de ruído configurado para o receptor).
- aumentar o ganho da antena de Morro do Jacu para 9 dBi: aproximadamente +7.0 dB (ganho direto no orçamento do enlace).
- reduzir cada perda de linha para aproximadamente 0,5 dB: aproximadamente +2.0 dB (redução direta no orçamento do enlace).

### Incertezas declaradas

- vegetação e edificações não estão representadas.
- o ruído local do receptor ainda não foi medido.
- erros verticais do DEM não são amostrados no Monte Carlo 0.1.

## Rastreabilidade

- SHA-256 do perfil: `01acb399bfedd326365f20faddff9e99e4adb000a23198821e8aecf21c5ddefe`
- Pontos do perfil: 6007
- Passo nominal: 30.002 m
- SHA-256 do resultado: `029328ba7d6ec068ca0b5a8e2893aeff1a35eb226db1c7662330fc31d7cd951b`

Os modelos permanecem separados; a divergência entre eles não é tratada como uma distribuição aleatória.
