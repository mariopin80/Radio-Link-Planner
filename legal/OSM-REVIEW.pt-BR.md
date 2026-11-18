# OpenStreetMap — verificação preliminar de utilização

**18/11/2026 — revisão estática, sem captura de tráfego na versão Windows.**

Decisão do proprietário: continuar utilizando os mapas públicos enquanto houver conformidade com as condições de uso e a escala continuar pequena. Não trocar o provedor neste trabalho.

## O que o código faz hoje

- `map_picker.py`, `report.py` e `coverage_report.py` utilizam `https://tile.openstreetmap.org/{z}/{x}/{y}.png` para o mapa de fundo, carregado de forma interativa via MapLibre.
- Não existe rotina de baixar regiões inteiras de imagens de mapas, nem exportação de pacotes de tiles offline.
- O terreno dos cálculos vem do **Copernicus**, não dos tiles do OSM.
- Atribuição visível: `© OpenStreetMap contributors`. Esta revisão passou a inserir também o link oficial https://www.openstreetmap.org/copyright nos controles de atribuição.
- O visualizador de coordenadas usa janela WebView sobre servidor HTTP local. Relatórios HTML também podem ser abertos diretamente do disco e possuem metatag de política de referenciador.

## Política oficial do servidor de tiles

https://operations.osmfoundation.org/policies/tiles/

| Item | Resultado |
| --- | --- |
| URL HTTPS oficial | Conforme no código |
| Crédito e link para a licença | Ajustado nos controles de atribuição |
| Acesso sob demanda, sem prefetch em massa | Código não implementa bulk download; confirmar em execução |
| Cache que respeita os cabeçalhos HTTP | Depende do mecanismo navegador/WebView; **aferir** |
| `User-Agent` próprio e estável para aplicativo | **Não configurado explicitamente** para as solicitações MapLibre; aferir na versão empacotada |
| `Referer` adequado quando operando como página web | **Aferir** no navegador, WebView e abertura de relatórios `file://` |
| SLA/uso comercial em escala | Não garantido pela OSMF; acesso pode ser bloqueado |

## Verificação necessária na próxima compilação Windows

1. Abrir seletor de coordenadas incorporado e um relatório HTML no WebView.
2. Capturar somente os cabeçalhos de requisições aos tiles: `User-Agent`, `Referer`, `Cache-Control` e `If-Modified-Since`/`If-None-Match`, sem guardar tokens nem dados pessoais.
3. Abrir relatório HTML a partir do disco (`file://`) e comparar os cabeçalhos, especialmente `Referer`.
4. Repetir uma mesma região para constatar a utilização do cache de acordo com o provedor.
5. Conferir visualmente o link de atribuição em mapa de enlace, cobertura e seletor.
6. Corrigir qualquer não conformidade identificada; se a tecnologia não permitir identificar o aplicativo ou fornecer o `Referer` exigido, substituir o serviço de tiles **antes** de distribuir o build correspondente.

### Limite da conclusão

O servidor público não proíbe automaticamente todo uso comercial, mas exige conformidade técnica e pode suspender acesso. **Ainda não há evidência suficiente para declarar que todos os cabeçalhos da versão Windows atual cumprem a política.** A decisão de continuar usando o servidor é operacional, não uma dispensa das condições de uso.
