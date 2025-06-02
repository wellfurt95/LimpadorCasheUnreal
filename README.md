# Documentação: Limpador de Cache Unreal Engine

**Versão:** 1.1 (Proposta)
**Data:** 02 de Junho de 2025

## 1. Introdução e Objetivo

O **Limpador de Cache Unreal Engine** é uma ferramenta desenvolvida para auxiliar usuários da Unreal Engine a gerenciar e limpar arquivos de cache temporários e derivados que são gerados durante o desenvolvimento de projetos. Esses arquivos, localizados em pastas como `Intermediate`, `DerivedDataCache` e diversas subpastas de `Saved`, podem ocupar um espaço considerável em disco com o tempo.

O objetivo principal deste programa é fornecer uma maneira fácil, segura e altamente configurável de liberar esse espaço, ajudando a manter o sistema organizado e otimizado, com opções de automação e controle granular.

## 2. Funcionalidades Principais

O programa oferece um conjunto robusto de funcionalidades para gerenciar os caches dos seus projetos Unreal Engine:

* **Descoberta de Projetos:**
    * **Automática:** Ao iniciar, o programa escaneia a pasta padrão de projetos da Unreal Engine (normalmente `Documentos\Unreal Projects`) para listar projetos.
    * **Manual:** Permite que o usuário adicione manualmente projetos localizados em qualquer diretório do sistema.
    * Botão para reescanear a pasta padrão, limpando a lista atual de projetos descobertos automaticamente e buscando novamente.
* **Persistência de Dados:**
    * A lista de projetos (descobertos e manuais), suas configurações individuais (monitoramento, permissão de limpeza, limite de GB) e as seleções de pastas/subpastas para limpeza são salvas em um arquivo de configuração (`clean_unreal_config.json`).
    * Configurações globais do aplicativo, como o intervalo de monitoramento e as preferências de inicialização, também são salvas.
    * Todos os dados são carregados automaticamente quando o programa é iniciado.
* **Gerenciamento Granular por Projeto:**
    * **Listagem Detalhada:** Para cada projeto, exibe nome e caminho.
    * **Controles Gerais do Projeto:**
        * `Monitorar Auto` (Checkbox): Define se o projeto será incluído nas verificações do monitoramento automático.
        * `Permitir Limpeza (Geral)` (Checkbox): Autorização principal para que qualquer limpeza (manual global ou automática) possa ocorrer neste projeto.
        * `Limite GB (Auto)` (Campo de Entrada): Define o tamanho máximo (em Gigabytes) que o cache *dos itens selecionados para limpeza* pode atingir antes que o monitoramento automático tente limpá-lo.
        * `Remover Projeto`: Botão para remover o projeto da lista do gerenciador.
    * **Seleção Detalhada de Itens para Limpeza:**
        * Para cada projeto, o usuário pode expandir seções para as pastas principais (`Intermediate`, `DerivedDataCache`, `Saved`).
        * Um checkbox para cada pasta principal permite selecionar a limpeza de **arquivos soltos** diretamente dentro dela (ex: `Saved (arquivos soltos na raiz desta pasta)`).
        * Subpastas diretas dentro de cada pasta principal são listadas dinamicamente, cada uma com seu próprio checkbox para seleção individual.
        * Descrições são fornecidas para subpastas conhecidas, auxiliando o usuário na decisão.
    * **Status do Cache:** Um campo exibe informações sobre o cache do projeto (ex: "Cache Total: X GB | Selecionado: Y MB") após a análise.
* **Ações Globais na Interface:**
    * **Analisar Todos os Projetos:** Calcula e exibe dois valores para cada projeto listado:
        1.  O tamanho total do cache "potencial" (definido atualmente como as pastas `Intermediate` e `DerivedDataCache` inteiras).
        2.  O tamanho combinado dos itens (arquivos soltos de pastas principais e/ou subpastas) que estão *atualmente selecionados* pelo usuário para limpeza naquele projeto.
    * **Limpar Projetos Permitidos:** Inicia a limpeza para todos os projetos listados que:
        1.  Têm a opção "Permitir Limpeza (Geral)" marcada.
        2.  Não estão atualmente abertos no editor da Unreal Engine.
        3.  Têm pelo menos um item (pasta principal para arquivos soltos ou subpasta) selecionado para limpeza.
        * A limpeza deleta os arquivos soltos e/ou subpastas explicitamente selecionados.
        * **Regra Adicional:** Se uma subpasta dentro de `Saved`, `Intermediate`, ou `DerivedDataCache` é limpa, os arquivos soltos na raiz dessa respectiva pasta principal também são automaticamente limpos.
        * Após a limpeza, a interface de seleção de subpastas para o projeto é atualizada para remover os itens que foram efetivamente deletados do disco.
* **Monitoramento Automático em Segundo Plano:**
    * **Ativação Configurável:** Uma opção "Ativar monitoramento automático ao iniciar o programa" permite que o monitoramento comece automaticamente quando o aplicativo é aberto.
    * **Controle Manual (UI e Bandeja):** Botões "Iniciar Monitoramento" e "Parar Monitoramento" na interface principal, e uma opção "Alternar Monitoramento" no menu da bandeja, permitem ligar/desligar o ciclo de monitoramento durante a sessão.
    * **Verificação Periódica:** Verifica os projetos configurados em intervalos definidos pelo usuário (em minutos).
    * **Lógica de Limpeza Automática:** Para cada projeto com "Monitorar Auto" e "Permitir Limpeza (Geral)" ativos, e que não esteja aberto no editor:
        1.  Calcula o tamanho do cache dos *itens selecionados* para limpeza.
        2.  Se este tamanho exceder o "Limite GB" definido para o projeto, a limpeza desses itens selecionados (e os arquivos soltos correspondentes, conforme a regra) é executada.
        3.  A interface de seleção é atualizada após a limpeza.
    * **Intervalo Configurável:** O usuário define o intervalo em minutos, que é salvo e carregado.
* **Interface Gráfica com Abas:**
    * **Aba "Gerenciador":** Contém todos os controles para listar e configurar projetos, executar ações globais e configurar o monitoramento.
    * **Aba "Logs":** Exibe um histórico detalhado das ações realizadas pelo programa, status, erros e informações de depuração, com timestamps.
* **Integração com a Bandeja do Sistema (System Tray):**
    * **Minimizar para Bandeja:** Ao clicar no botão "X", a janela principal é minimizada para a bandeja, e o programa continua ativo.
    * **Ícone Personalizado:** Exibe o ícone do programa na bandeja.
    * **Menu de Contexto na Bandeja:**
        * `Abrir Limpador`: Restaura a janela principal.
        * `Monitoramento > Alternar Monitoramento`: Liga ou desliga o monitoramento automático.
        * `Monitoramento > Status: [Ativo/Parado]`: Exibe o estado atual do monitoramento.
        * `Fechar Limpador`: Salva as configurações e encerra o programa completamente.
    * **Duplo Clique no Ícone:** Abre/restaura a janela principal.
* **Inicialização com o Windows:**
    * Opção "Iniciar com o Windows" na interface que configura o programa para ser executado automaticamente na inicialização do sistema (via Registro do Windows).

## 3. Como Usar o Programa

1.  **Instalação e Primeira Execução:**
    * Execute o arquivo `LimpadorUnreal.exe`.
    * Na primeira execução, nenhum projeto estará configurado. O programa tentará escanear a pasta padrão `Documentos\Unreal Projects`.
    * Use o botão "**Adicionar Projeto Manualmente**" para incluir projetos de outros locais.
    * O botão "**Escanear Pasta Padrão Novamente**" limpa a lista de projetos descobertos automaticamente e reescaneia a pasta padrão (não afeta projetos adicionados manualmente, a menos que eles também estejam na pasta padrão e sejam re-descobertos).

2.  **Configurando Cada Projeto (Aba "Gerenciador"):**
    * Para cada projeto listado:
        * **Monitorar Auto:** Marque para incluir nas verificações do monitoramento automático.
        * **Permitir Limpeza (Geral):** Autorização principal para qualquer tipo de limpeza (manual ou automática) neste projeto.
        * **Limite GB (Auto):** Se "Monitorar Auto" estiver ativo, defina o tamanho máximo em GB para o *cache dos itens selecionados abaixo* antes da limpeza automática.
        * Clique no botão "**Mostrar Subpastas de [Saved/Intermediate/DerivedDataCache] ▼**" para expandir a lista de itens limpáveis para aquela categoria.
        * Marque os checkboxes das **pastas principais** (ex: `[ ] Saved (arquivos soltos...)`) se desejar limpar os arquivos que estão diretamente na raiz daquela pasta.
        * Marque os checkboxes das **subpastas específicas** (ex: `[ ] Saved\Logs`) que você deseja incluir na limpeza.
        * Use o botão "**Remover Projeto**" para tirar um projeto da lista.

3.  **Ações Manuais Globais (Aba "Gerenciador"):**
    * Clique em "**Analisar Todos os Projetos**" para ver o "Cache Total Potencial" (Intermediate + DDC) e o tamanho do "Cache Selecionado" para cada projeto.
    * Clique em "**Limpar Projetos Permitidos**" para limpar os itens selecionados nos projetos que têm "Permitir Limpeza (Geral)" marcado e estão fechados no editor. Após a limpeza, as subpastas deletadas sumirão da lista de seleção.

4.  **Monitoramento Automático (Aba "Gerenciador"):**
    * Marque "**Ativar monitoramento automático ao iniciar o programa**" para que o monitoramento comece quando o aplicativo for aberto.
    * Defina o "**Intervalo (minutos):**" para a frequência das verificações.
    * Use os botões "**Iniciar Monitoramento**" e "**Parar Monitoramento**" para controlar o ciclo manualmente durante a sessão.
    * O status do monitoramento ("Ativo", "Parando...", "Parado", "Verificando...") será exibido.

5.  **Usando a Bandeja do Sistema:**
    * Fechar a janela principal (botão "X") minimiza o programa para a bandeja.
    * **Duplo clique** no ícone da bandeja restaura a janela.
    * **Clique com o botão direito** no ícone para: `Abrir Limpador`, `Alternar Monitoramento` ou `Fechar Limpador` (que encerra o programa de vez).

6.  **Visualizando Logs (Aba "Logs"):**
    * Acompanhe todas as ações importantes, status e erros do programa nesta aba.

7.  **Iniciando com o Windows (Aba "Gerenciador"):**
    * Marque a opção "**Iniciar com o Windows**" para configurar o início automático. Desmarcar remove a configuração.

## 4. Arquivo de Configuração (`clean_unreal_config.json`)

Localizado na mesma pasta do executável, salva:
* **Configurações Globais:** `auto_start_monitoring_on_launch`, `monitoring_interval_seconds`, `start_with_windows`.
* **Lista de Projetos:** Para cada um: `path`, `name`, `uproject_file`, `monitor_auto`, `allow_clean`, `gb_limit`, e `selected_cleanup_items` (lista dos identificadores das pastas principais e caminhos relativos das subpastas selecionadas para limpeza).

## 5. Pastas de Cache Alvo para Limpeza Granular

O usuário seleciona quais dos seguintes itens deseja limpar para cada projeto:
* Arquivos soltos diretamente dentro de `Intermediate`.
* Subpastas de `Intermediate` (ex: `Build`, `ProjectFiles`).
* Arquivos soltos diretamente dentro de `DerivedDataCache`.
* Subpastas de `DerivedDataCache` (ex: `VT`).
* Arquivos soltos diretamente dentro de `Saved`.
* Subpastas de `Saved` (ex: `Logs`, `Crashes`, `Autosaves`).

**A limpeza de arquivos soltos em uma pasta principal (`Saved`, `Intermediate`, `DerivedDataCache`) ocorre se o checkbox da pasta principal estiver marcado OU se alguma subpasta dentro dela for selecionada e limpa.**

## 6. Considerações Importantes e Avisos

* **Segurança:** O programa verifica se um projeto está aberto antes de limpá-lo. Feche a Unreal Engine antes de limpezas manuais extensas.
* **Permissão de Limpeza (Geral):** É a chave mestra para qualquer limpeza em um projeto.
* **Reconstrução de Cache:** A Unreal Engine recriará os caches limpos, o que pode levar tempo ao abrir o projeto.
* **Backup de Projetos:** Mantenha backups dos seus projetos importantes.
* **Pastas Críticas:** Tenha extremo cuidado ao considerar limpar itens dentro de `Saved/Config` ou `Saved/SaveGames`. O programa permite selecionar subpastas, mas a responsabilidade da seleção é do usuário. Por padrão, estas não são recomendadas para limpeza automática.

## 7. Como Compilar (Usando PyInstaller)

1.  Instale as dependências (Python, customtkinter, pystray, Pillow, psutil).
2.  Tenha um ícone `CleanUnreal.ico` na pasta raiz do projeto.
3.  Use o comando no terminal, na pasta do projeto:
    ```bash
    python -m PyInstaller --name LimpadorUnreal --noconsole --onefile --icon=CleanUnreal.ico --add-data "CleanUnreal.ico:." app.py
    ```
4.  O executável estará em `dist/LimpadorUnreal/LimpadorUnreal.exe`.
