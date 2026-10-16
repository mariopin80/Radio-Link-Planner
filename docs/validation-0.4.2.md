# Validação da versão 0.4.2

Ambiente de desenvolvimento: Linux x64, Python 3.11, NumPy 2.3.5,
Rasterio 1.5.2; implementações P.1812 e P.2001 fixadas nos commits
registrados em `pyproject.toml`. Estes resultados não são uma medição
no computador Windows do usuário nem uma extrapolação validada a 500 km.

## Equivalência numérica

- 72 perfis comparados à Py1812 original: 0,25 a 500 km, amostragem de 30 m,
  30 MHz a 3 GHz, percentuais de 1, 10 e 50%, duas polarizações, terreno
  plano, ondulado, obstrução isolada, clutter e zonas terrestres/marítimas.
  Perdas e campos elétricos idênticos nas comparações executadas.
- Pixels preparados comparados ao leitor anterior incluindo fronteiras de
  pixels/tiles, nodata, zeros isolados, mar, reentrada em tiles e expulsão
  do cache de mapeamentos. A seleção usa a operação `rowcol` do Rasterio
  para preservar sua ordem de arredondamento.
- Grade real com 7.845 células: quatro tiles Copernicus ao redor de
  23° S, 47° W; raio 50 km, células de 1 km, perfis a 30 m, 146 MHz,
  polarização vertical, 50% do tempo, TX a 30 m e RX a 2 m.
  As grades anterior/otimizada e um/quatro processos foram idênticas,
  incluindo as posições sem dados. Foram processadas 8.723.468 amostras.

## Desempenho medido

| Etapa de cálculo | Tempo |
|---|---:|
| Versão 0.4.1, um processo | 24,07 s |
| Versão 0.4.2, um processo | 7,34 s |
| Versão 0.4.2, quatro processos | 2,57 s |

Ganho de 3,28 vezes com um processo. Downloads iniciais, preparação dos
pixels e renderização não estão incluídos nesses tempos de cálculo.
O paralelismo existente permanece ativo; não houve redução da amostragem
nem interpolação de propagação entre células.

## Reutilização e retomada

Os testes verificam que alterações de orçamento reutilizam perdas em
precisão dupla e produzem a mesma grade que um recálculo completo; mudanças
físicas invalidam a reutilização. A integridade da grade é conferida por
SHA-256. Cancelamento, retomada e liberação dos arquivos mapeados são
exercitados, assim como a recuperação após corrupção do cache final.

## Empacotamento

O workflow Windows instala as dependências e os produtos científicos,
executa a suíte, compila o executável e o instalador, testa o aplicativo
portátil e instalado (inclusive o carregamento do ícone e da tela inicial),
testa a desinstalação e gera hashes dos dois pacotes antes da publicação.
