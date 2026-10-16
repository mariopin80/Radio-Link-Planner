# Validação da versão 0.5

## Execução local

- 81 testes automatizados, incluindo as referências ITM, P.1812 e P.2001, executados com os componentes científicos instalados.
- Interface exercitada nos cinco idiomas: seletores, polarização, resolução, projetos novos e antigos, aba Sobre e tempo restante em um único local.
- Cinco análises completas do enlace de referência (500 execuções Monte Carlo por modelo), com HTML, PDF, perfil e gráficos. Resultados científicos idênticos entre os idiomas, desconsiderando apenas a data e o hash de cada execução.
- Grade de 81 células com GeoTIFFs sintéticos controlados, processamento em dois processos, geração de produtos e reutilização das perdas para emitir os relatórios em cinco idiomas. Todas as grades idênticas.
- Cobertura de 50 km com DEM Copernicus real, células de 1.000 m e perfis de 30 m: 7.845 células e 8.723.468 pontos de perfil. Grade idêntica à referência anterior, incluindo as posições sem dados.
- Dez PDFs renderizados para inspeção de paginação, tabelas e caracteres; contagens e cabeçalhos conferidos por extração. JavaScript dos mapas validado por Node.

Os cenários reduzidos de empacotamento verificam a integração e não constituem medição de desempenho de uma cobertura de 300 km.

## Verificações do pacote Windows

O workflow exige as seguintes verificações antes de disponibilizar a pré-versão:

1. Suíte automatizada com bibliotecas e dados científicos oficiais.
2. Executável portátil real: modelos, processo filho de cobertura, componentes geográficos e servidor local de relatórios.
3. Executável portátil real: telas e relatórios nos cinco idiomas, com igualdade numérica e inspeção dos PDFs e do JavaScript.
4. Instalação da 0.4.3 e atualização com o instalador 0.5 no mesmo diretório.
5. Atalhos reais do menu Iniciar e da área de trabalho apontando para o ícone da 0.5; decodificação nativa do ICO.
6. Aplicativo instalado: repetição das verificações científicas, geográficas, de interface e relatórios nos cinco idiomas.
7. Dados ITU-R no perfil do usuário e ausência de redistribuição dos produtos digitais integrais.
8. Desinstalação e geração dos hashes SHA-256 do instalador e ZIP.

A publicação é uma pré-versão no repositório privado. A avaliação de uso do desenvolvedor antecede a decisão de lançar a versão 1.0.
