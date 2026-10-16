# Validação da versão 0.5.1

O workflow Windows exige estas verificações antes de publicar os pacotes:

1. Suíte científica e de interface, incluindo as referências ITM, P.1812 e P.2001.
2. Tela inicial nos cinco idiomas, em 1180 × 760 e 900 × 600: descrições em uma linha, conteúdos dentro dos cartões e sem sobreposição com as ações. Capturas de tela preservadas nos artefatos de validação.
3. Linha de autoria no Sobre, projetos novos e anteriores e tempo restante em um único local.
4. Executável portátil real: análise do enlace e cobertura, relatórios HTML/PDF e mapas nos cinco idiomas, preservando a igualdade dos resultados numéricos.
5. Instalação da versão 0.5 e atualização para 0.5.1 no mesmo diretório; atalhos reais e decodificação nativa do ICO.
6. Aplicativo instalado: repetição dos testes de interface, cálculos e relatórios.
7. Desinstalação e hashes SHA-256 do instalador e da versão portátil.

Os testes de empacotamento usam cenários reduzidos de cobertura e não medem o tempo de uma cobertura de 300 km. A referência detalhada da versão anterior permanece em `validation-0.5.md`.
