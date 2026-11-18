# Radio Link Planner 0.5.3 RC1 — pré-lançamento para testes

Novembro de 2026 · Mario Pin — PU2PTU

Esta é uma **pré-release** para validar a visualização da cobertura e a exportação de mapas geográficos em PDF. A versão estável 0.5.2 continua disponível.

## Novidades

- Alternância no mapa de cobertura entre **Margem (dB)** e **Escala S**, preservando a margem como padrão.
- Contornos S1, S3, S5, S7 e S9+ baseados na potência recebida estimada. Para VHF/UHF, usa-se a referência S9 = −93 dBm e 6 dB por unidade S; não representa uma medição real do S-meter de um rádio.
- Botão **Exportar PDF com este mapa**, que incorpora a captura da visualização geográfica atual — OpenStreetMap, cobertura, contornos, marcador da estação, legenda e atribuição — ao relatório em PDF.
- O usuário escolhe a escala e o enquadramento no navegador antes de exportar. A captura usa o mapa interativo já carregado; não faz varredura automática de tiles do OpenStreetMap.
- O aplicativo salva `coverage_map_geographic.png` e `relatorio_cobertura_com_mapa.pdf` na pasta da análise, além do PDF técnico original.
- Traduções atualizadas em português, inglês, espanhol, francês e alemão; documentação e testes de segurança ampliados.

## Como testar

1. Instale o programa ou extraia a versão portátil.
2. Execute um cálculo de cobertura e abra o mapa interativo.
3. Alterne entre **Margem (dB)** e **Escala S**. Confira se a legenda e os contornos mudam.
4. Ajuste zoom e posição; clique em **Exportar PDF com este mapa**.
5. Confira se o PDF baixado contém o mesmo mapa geográfico, incluindo os créditos OpenStreetMap, e se os dois arquivos novos foram salvos na pasta do projeto.

## Downloads

- **RadioLinkPlanner-0.5.3rc1-Windows-x64-Setup.exe**: instalador Windows x64.
- **RadioLinkPlanner-0.5.3rc1-Windows-x64.zip**: versão portátil.
- **SHA256SUMS.txt**: hashes SHA-256 para conferência de integridade.

## Limitações e licenças

As áreas de cobertura e os valores S são estimativas do modelo, não garantias de operação em campo. A exportação geográfica depende da disponibilidade dos tiles no navegador e é iniciada manualmente.

Esta edição não implementa ainda os mecanismos comerciais Community/Personal/Pro. Mantêm-se os avisos de licenças de terceiros da 0.5.2 e a restrição de **não redistribuir** os arquivos digitais integrais da ITU.
