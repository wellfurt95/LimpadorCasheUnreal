Documentação: Limpador de Cache Unreal Engine
Versão: 1.0 (Proposta)
Data: 31 de Maio de 2025

1. Introdução e Objetivo
O Limpador de Cache Unreal Engine é uma ferramenta desenvolvida para auxiliar usuários da Unreal Engine a gerenciar e limpar arquivos de cache temporários e derivados que são gerados durante o desenvolvimento de projetos. Esses arquivos, localizados em pastas como Intermediate, DerivedDataCache e subpastas de Saved, podem ocupar um espaço considerável em disco com o tempo.

O objetivo principal deste programa é fornecer uma maneira fácil, segura e parcialmente automatizada de liberar esse espaço, ajudando a manter o sistema organizado e otimizado.

2. Funcionalidades Principais
O programa oferece um conjunto robusto de funcionalidades para gerenciar os caches dos seus projetos Unreal Engine:

Descoberta de Projetos:
Automática: Ao iniciar, o programa pode escanear a pasta padrão de projetos da Unreal Engine (normalmente Documentos\Unreal Projects) para listar seus projetos.
Manual: Permite que o usuário adicione manualmente projetos localizados em qualquer diretório do sistema.
Persistência de Dados:
A lista de projetos adicionados (automática e manualmente) e suas configurações individuais (limite de GB, permissões de limpeza, etc.) são salvas em um arquivo de configuração (clean_unreal_config.json).
Esses dados são carregados automaticamente sempre que o programa é iniciado.
Gerenciamento por Projeto:
Nome e Caminho: Exibe o nome e o caminho de cada projeto listado.
Status do Cache: Um campo exibe informações sobre o cache do projeto (tamanho após análise, status da limpeza).
Monitorar Auto (Checkbox): Define se o projeto será incluído nas verificações do monitoramento automático em segundo plano.
Permitir Limpeza (Checkbox): Autoriza o programa a limpar o cache do projeto (seja pela ação global manual ou pelo monitoramento automático). Essencial para a segurança.
Limite GB (Auto) (Campo de Entrada): Define o tamanho máximo (em Gigabytes) que o cache de um projeto pode atingir antes que o monitoramento automático tente limpá-lo (requer "Monitorar Auto" e "Permitir Limpeza" ativos).
Ações Globais na Interface:
Analisar Todos os Projetos: Calcula e exibe o tamanho atual do cache (pastas Intermediate e DerivedDataCache) para todos os projetos listados.
Limpar Projetos Permitidos: Inicia a limpeza do cache para todos os projetos listados que têm a opção "Permitir Limpeza" marcada e que não estão atualmente abertos no editor da Unreal Engine.
Monitoramento Automático em Segundo Plano:
Ativação: Pode ser configurado para iniciar automaticamente quando o programa é aberto através da opção "Ativar monitoramento automático ao iniciar o programa".
Verificação Periódica: Verifica os projetos configurados em intervalos definidos pelo usuário.
Lógica de Limpeza Automática: Se um projeto estiver com "Monitorar Auto" e "Permitir Limpeza" ativos, não estiver aberto no editor, e seu cache (Intermediate + DerivedDataCache) exceder o "Limite GB" definido, a limpeza será executada automaticamente.
Intervalo Configurável: O usuário pode definir o intervalo (em segundos) entre os ciclos de verificação do monitoramento automático. Este valor é salvo.
Interface Gráfica com Abas:
Aba "Gerenciador": Contém todos os controles para listar, configurar projetos, e executar ações globais.
Aba "Logs": Exibe um histórico de ações realizadas pelo programa, mensagens de status, erros e informações de depuração.
Integração com a Bandeja do Sistema (System Tray):
Minimizar para Bandeja: Ao clicar no botão "X" para fechar a janela principal, o programa é minimizado para a bandeja do sistema, continuando a rodar em segundo plano (especialmente o monitoramento automático, se ativo).
Ícone Personalizado: Exibe um ícone do programa na bandeja.
Menu de Contexto na Bandeja:
Abrir Limpador: Restaura e exibe a janela principal do programa.
Alternar Monitoramento: Permite iniciar ou parar manualmente o ciclo de monitoramento automático durante a sessão atual.
Fechar Limpador: Encerra completamente o programa (salvando as configurações antes).
Duplo Clique no Ícone: Abre a janela principal do programa.
Inicialização com o Windows:
Possui uma opção na interface ("Iniciar com o Windows") que, quando marcada, configura o programa para ser executado automaticamente na inicialização do sistema operacional (no Windows, isso é feito via uma entrada no Registro).
3. Como Usar o Programa
Primeira Execução e Adição de Projetos:

Ao iniciar pela primeira vez, o programa tentará carregar projetos de um arquivo de configuração (que não existirá). Em seguida, ele fará uma varredura na pasta padrão (Documentos\Unreal Projects).
Use o botão "Adicionar Projeto Manualmente" para incluir projetos que estejam em outros locais.
O botão "Escanear Pasta Padrão Novamente" permite limpar a lista atual (exceto os carregados manualmente que já estavam lá e não foram limpos por esta ação) e buscar novamente na pasta padrão.
Configurando Cada Projeto:

Para cada projeto listado na aba "Gerenciador":
Monitorar Auto: Marque esta caixa se você deseja que o monitoramento automático em segundo plano verifique este projeto.
Permitir Limpeza: Marque esta caixa para dar permissão ao programa para limpar o cache deste projeto. Sem esta permissão, nenhuma limpeza (manual global ou automática) ocorrerá para este projeto.
Limite GB (Auto): Se "Monitorar Auto" estiver ativo, defina aqui o tamanho máximo em GB que o cache (Intermediate + DerivedDataCache) pode atingir antes que a limpeza automática seja acionada. Deixe em branco ou com 0 se não quiser um limite específico para o monitoramento automático (embora um valor seja necessário para a lógica de > limite).
Ações Manuais Globais:

Clique em "Analisar Todos os Projetos" para que o programa calcule e exiba o tamanho atual das pastas Intermediate e DerivedDataCache de cada projeto listado no campo "Cache:".
Clique em "Limpar Projetos Permitidos" para executar a limpeza do cache (Intermediate e DerivedDataCache) de todos os projetos que estiverem com a opção "Permitir Limpeza" marcada e que não estejam abertos no editor da Unreal Engine.
Monitoramento Automático:

Na seção "Configurações de Monitoramento":
Marque "Ativar monitoramento automático ao iniciar o programa" se desejar que o programa comece a monitorar seus projetos em segundo plano assim que for iniciado.
Defina o "Intervalo (segundos):" para determinar com que frequência o monitoramento verificará os projetos (ex: 3600 para uma vez por hora).
O status do monitoramento ("Ativo", "Parando...", "Parado", "Verificando...") será exibido.
O monitoramento só limpará projetos que tenham "Monitorar Auto" e "Permitir Limpeza" ativos, não estejam abertos, e cujo cache exceda o "Limite GB".
Usando a Bandeja do Sistema:

Ao clicar no "X" da janela principal, ela será escondida, mas o programa continuará rodando com um ícone na bandeja do sistema.
Duplo clique no ícone da bandeja restaura a janela.
Clique com o botão direito no ícone da bandeja para acessar:
Abrir Limpador: Mostra a janela principal.
Alternar Monitoramento: Liga ou desliga o ciclo de monitoramento automático.
Fechar Limpador: Salva todas as configurações e encerra o programa completamente.
Visualizando Logs:

Acesse a aba "Logs" na interface principal para ver um histórico das principais ações realizadas pelo programa, status e possíveis erros.
Iniciando com o Windows:

Marque a opção "Iniciar com o Windows" (na seção de Configurações de Monitoramento ou similar) para que o programa seja configurado para iniciar automaticamente toda vez que você ligar o seu computador. Desmarcar a opção remove essa configuração.
4. Arquivo de Configuração (clean_unreal_config.json)
O programa salva suas configurações e a lista de projetos em um arquivo chamado clean_unreal_config.json, localizado na mesma pasta do executável. Este arquivo armazena:

Configurações Globais:
auto_start_monitoring_on_launch: Se o monitoramento automático deve iniciar com o programa.
monitoring_interval_seconds: O intervalo de verificação do monitoramento.
(Opcional, dependendo da implementação) start_with_windows: Se o programa está configurado para iniciar com o Windows.
Lista de Projetos: Para cada projeto:
path: O caminho completo para a pasta do projeto.
name: O nome do projeto.
uproject_file: O nome do arquivo .uproject.
monitor_auto: Estado do checkbox "Monitorar Auto".
allow_clean: Estado do checkbox "Permitir Limpeza".
gb_limit: O valor definido no campo "Limite GB (Auto)".
5. Pastas de Cache Alvo
Por padrão, o programa foca na limpeza das seguintes pastas dentro de cada projeto Unreal:

Intermediate
DerivedDataCache
Estas pastas geralmente contêm a maior parte dos dados de cache regeneráveis e são seguras para limpar quando o editor está fechado.

6. Considerações Importantes e Avisos
Segurança Primeiro: O programa inclui uma verificação para tentar determinar se um projeto Unreal está aberto antes de limpá-lo. No entanto, é sempre uma boa prática salvar seu trabalho e fechar a Unreal Engine antes de realizar limpezas de cache extensas, especialmente usando o botão "Limpar Projetos Permitidos".
Permissão de Limpeza: Nenhum cache de projeto será limpo (nem manualmente nem automaticamente) a menos que o respectivo checkbox "Permitir Limpeza" esteja marcado para aquele projeto.
Reconstrução de Cache: Após a limpeza das pastas Intermediate e DerivedDataCache, a Unreal Engine precisará recriar esses arquivos na próxima vez que o projeto for aberto. Isso pode levar algum tempo, especialmente para projetos grandes.
Backup: Embora o programa vise pastas de cache que são geralmente seguras para deletar, ter um sistema de backup regular para seus projetos importantes é sempre uma prática recomendada.