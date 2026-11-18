# Prévia — Aviso de Privacidade e Ativação Online

**MINUTA NÃO VIGENTE. O sistema de licenciamento online ainda não foi implementado.**

Documento preparatório para atender à Lei 13.709/2018 (LGPD); requer conferência da arquitetura final e revisão jurídica.

**Controlador:** [RAZÃO SOCIAL OU TITULAR], [CONTATO/ENDEREÇO].

**Canal para solicitações de dados:** [E-MAIL].

## 1. Dados mínimos propostos

| Informação | Uso previsto | Coletar? |
| --- | --- | --- |
| E-mail de cadastro | Criar conta, recuperar acesso e enviar recibos | Sim, no cadastro pago |
| Identificador da licença e edição | Autorizar funções e prevenir reutilização indevida | Sim |
| Identificador técnico pseudonimizado do dispositivo | Contar ativações e permitir transferência segura | Apenas se necessário; sem número de série em texto puro |
| Data e resultado da ativação | Auditoria de segurança e suporte | Sim, com prazo de retenção limitado |
| Pagamento | Confirmação de compra e dados fiscais | Preferir provedor especializado; **não** armazenar dados do cartão |
| Localização e perfis de terreno dos projetos | Cálculo técnico local | Não enviar ao servidor de licença |
| Dados de uso/telemetria ou marketing | Métricas e publicidade | Não habilitar por padrão; avaliar finalidade e base legal separadamente |

## 2. Finalidades e bases legais

Os tratamentos necessários ao fornecimento e à administração da licença poderão ser fundamentados na execução de contrato e, quando pertinente, em obrigação legal ou outro fundamento adequado conforme a LGPD. Não utilizar consentimento genérico como substituto automático da base legal correta. Mensagens de marketing terão tratamento separado do serviço essencial.

## 3. Fluxo de ativação proposto

1. Cliente informa e verifica o e-mail.
2. Servidor confirma edição, situação da contratação e número de dispositivos ativos.
3. O aplicativo recebe credencial de licença assinada digitalmente, sem conter segredos reutilizáveis do servidor.
4. O programa verifica a assinatura localmente e continua executando os cálculos offline por prazo ainda a definir.
5. Troca de computador, revogação e recuperação de conta terão procedimentos de suporte claros.

## 4. Compartilhamento, segurança e hospedagem

Identificar antes do lançamento os operadores de hospedagem, e-mail e pagamento, seus países e regras de transferência internacional quando aplicáveis. Proteger a comunicação com HTTPS/TLS, credenciais, banco de dados, chaves privadas e backups. Definir controle de acesso, resposta a incidentes, logs necessários e retenção. Não armazenar a senha do usuário em texto puro.

## 5. Retenção e direitos do titular

Definir prazos específicos para contas, licenças, logs e registros fiscais. Disponibilizar canal para consulta, correção, acesso e pedidos de eliminação, observadas as hipóteses legais de conservação. Informar o prazo de resposta e os contatos do controlador.

## 6. Software Community

Proposta: utilização gratuita sem cadastro compulsório e sem envio de dados pessoais ao nosso servidor. Downloads de mapas/terreno e eventuais acessos aos fornecedores externos continuam sujeitos às suas políticas próprias. Se houver mecanismo futuro de autenticação na Community, este aviso deverá ser atualizado e os usuários informados.

## 7. Dados a completar

- [ ] Entidade controladora e canal de atendimento.
- [ ] Fornecedor e localização da hospedagem.
- [ ] Serviço de cobrança e suas responsabilidades.
- [ ] Periodicidade de revalidação offline.
- [ ] Critério de identificador de dispositivo e política de trocas.
- [ ] Prazos de retenção, descarte e backup.
- [ ] Base legal por tratamento e eventual transferência internacional.
- [ ] Política de privacidade pública aprovada e versionada.

Referências oficiais: https://www.gov.br/anpd/pt-br/assuntos/titular-de-dados/direito-dos-titulares e https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia-orientativo-sobre-seguranca-da-informacao-para-agentes-de-tratamento-de-pequeno-porte.
