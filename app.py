import customtkinter as ctk
import os
import threading
import time
from tkinter import filedialog
import shutil
import math
import psutil
import json
import pystray
from PIL import Image
import sys
import winreg

if hasattr(sys, "frozen") and sys.frozen:  # Rodando como .exe (PyInstaller)
    APPLICATION_PATH = os.path.dirname(sys.executable)
else:  # Rodando como script .py
    try:
        APPLICATION_PATH = os.path.dirname(os.path.abspath(__file__))
    except (
        NameError
    ):  # __file__ não é definido em alguns contextos (ex: console interativo)
        APPLICATION_PATH = os.path.abspath(".")
POTENTIAL_CACHE_MAIN_FOLDERS = ["Intermediate", "DerivedDataCache", "Saved"]
CONFIG_FILE_NAME = "clean_unreal_config.json"
ABSOLUTE_CONFIG_PATH = os.path.join(APPLICATION_PATH, CONFIG_FILE_NAME)

# --- Configurações Iniciais ---
user_home_path = os.path.expanduser("~")
UNREAL_PROJECTS_DEFAULT_PATH = os.path.join(
    user_home_path, "Documents", "Unreal Projects"
)
KNOWN_SUBFOLDER_DESCRIPTIONS = {
    os.path.normpath("Saved/Logs"): "Logs de execução do editor e do jogo.",
    os.path.normpath("Saved/Crashes"): "Relatórios de crash.",
    os.path.normpath(
        "Saved/Autosaves"
    ): "Cópias de segurança automáticas de assets e mapas.",
    os.path.normpath(
        "Saved/Config"
    ): "Arquivos de configuração (NÃO RECOMENDADO LIMPAR).",
    os.path.normpath(
        "Saved/SaveGames"
    ): "Arquivos de jogos salvos (NÃO RECOMENDADO LIMPAR).",
    # Removido: os.path.normpath("Saved/Intermediate"): "Subpasta 'Intermediate' dentro de 'Saved' (raro).",
    # Removido: os.path.normpath("Saved/DerivedDataCache"): "Subpasta 'DerivedDataCache' dentro de 'Saved' (raro).",
    os.path.normpath("Saved/SourceControl"): "Informações de controle de versão.",
    os.path.normpath(
        "Saved/Telemetry"
    ): "Dados de telemetria (geralmente seguro limpar).",
    # Se você tem um webcache específico, mantenha. Se o nome varia, precisaria de outra lógica.
    # os.path.normpath("Saved/webcache_4430"): "Cache de conteúdo web específico do editor.",
    os.path.normpath("Intermediate/Build"): "Arquivos de compilação da plataforma.",
    os.path.normpath(
        "Intermediate/ProjectFiles"
    ): "Arquivos de projeto do IDE (Visual Studio, etc.).",
    # Adicione mais subpastas de Intermediate que você vê na sua imagem image_59c8da.png
    os.path.normpath("Intermediate/DataprepTemp"): "Arquivos temporários do Dataprep.",
    os.path.normpath(
        "Intermediate/DatasmithContentTemp"
    ): "Arquivos temporários de conteúdo Datasmith.",
    os.path.normpath(
        "Intermediate/PipInstall"
    ): "Arquivos relacionados à instalação de pacotes Python via pip (se usado).",
    os.path.normpath(
        "Intermediate/ReimportCache"
    ): "Cache para o processo de reimportação de assets.",
    os.path.normpath("Intermediate/ShaderAutogen"): "Shaders gerados automaticamente.",
    os.path.normpath("DerivedDataCache/VT"): "Cache de Virtual Texturing.",
    # Se houver outras subpastas comuns em DerivedDataCache, adicione aqui.
}

# --- Funções de Backend (Lógica do Programa) ---


def calculate_project_total_potential_cache(project_path, app_instance):
    """
    Calcula o tamanho total das pastas de cache "potencial" (ex: Intermediate, DerivedDataCache inteiras).
    """
    total_size = 0
    app_instance.log_message(
        f"CALC_TOTAL_POTENTIAL: Iniciando para '{project_path}'...", level="DEBUG"
    )

    for folder_name in POTENTIAL_CACHE_MAIN_FOLDERS:
        abs_folder_path = os.path.join(project_path, folder_name)
        app_instance.log_message(
            f"CALC_TOTAL_POTENTIAL: Verificando pasta '{abs_folder_path}'...",
            level="TRACE",
        )
        if os.path.exists(abs_folder_path) and os.path.isdir(abs_folder_path):
            try:
                folder_size = get_folder_size(
                    abs_folder_path
                )  # Usa a função get_folder_size que já existe
                app_instance.log_message(
                    f"CALC_TOTAL_POTENTIAL: Tamanho de '{folder_name}': {format_size(folder_size)}",
                    level="DEBUG",
                )
                total_size += folder_size
            except Exception as e:
                app_instance.log_message(
                    f"CALC_TOTAL_POTENTIAL: Erro ao calcular tamanho de '{abs_folder_path}': {e}",
                    level="ERROR",
                )
        else:
            app_instance.log_message(
                f"CALC_TOTAL_POTENTIAL: Pasta '{abs_folder_path}' não encontrada.",
                level="DEBUG",
            )

    app_instance.log_message(
        f"CALC_TOTAL_POTENTIAL: Tamanho total potencial para '{project_path}': {format_size(total_size)}",
        level="INFO",
    )
    return total_size


def discover_unreal_projects(base_path, app_instance, clear_ui_on_start=False):
    """
    Procura por pastas de projeto Unreal no caminho base fornecido.
    Uma pasta é considerada um projeto se contiver um arquivo .uproject.
    Esta função é destinada a rodar em uma thread separada.

    Args:
        base_path (str): O caminho da pasta onde procurar os projetos.
        app_instance (App): A instância da classe principal da aplicação (para callbacks via self.after).
        clear_ui_on_start (bool): Embora passado, esta função não limpa a UI diretamente.
                                   A lógica de limpeza da UI antes da varredura é feita
                                   em start_discover_projects_thread na classe App.
    """
    # Log inicial pode ser feito pela app_instance se ela tiver o método log_message
    # Ex: app_instance.log_message(f"Backend: Iniciando descoberta de projetos em {base_path}...", level="DEBUG")
    # Ou um print simples se preferir manter esta função mais independente:
    print(f"Backend (discover_unreal_projects): Procurando projetos em {base_path}...")

    found_projects = []
    if not os.path.exists(base_path):
        print(
            f"Backend (discover_unreal_projects): Caminho não encontrado: {base_path}"
        )
        # Envia uma mensagem de erro para a UI através da instância da App
        # A chamada para app_instance.update_project_list_ui_from_discovery está correta aqui
        app_instance.after(
            0,
            app_instance.update_project_list_ui_from_discovery,
            [],
            f"Caminho de projetos ('{base_path}') não encontrado.",
        )
        return

    try:
        for item_name in os.listdir(base_path):
            item_path = os.path.join(base_path, item_name)
            if os.path.isdir(item_path):
                # Verifica se existe um arquivo .uproject dentro desta pasta
                uproject_filename = None
                for sub_item in os.listdir(item_path):
                    if sub_item.endswith(".uproject"):
                        uproject_filename = (
                            sub_item  # Guarda o nome do arquivo .uproject
                        )
                        break  # Encontrou o .uproject, pode ir para o próximo item_name

                if uproject_filename:  # Se um arquivo .uproject foi encontrado
                    project_name = item_name  # O nome da pasta é o nome do projeto
                    project_data = {
                        "name": project_name,
                        "path": os.path.normpath(
                            item_path
                        ),  # Salva o caminho já normalizado
                        "uproject_file": uproject_filename,
                    }
                    found_projects.append(project_data)
                    print(
                        f"Backend (discover_unreal_projects): Projeto encontrado: {project_name} em {item_path} (Arquivo: {uproject_filename})"
                    )

        # Após encontrar os projetos, pede para a thread principal da UI atualizar a lista
        if not found_projects:
            print(
                f"Backend (discover_unreal_projects): Nenhum projeto Unreal encontrado em {base_path}."
            )
            app_instance.after(
                0,
                app_instance.update_project_list_ui_from_discovery,
                [],
                "Nenhum projeto Unreal encontrado na pasta padrão.",
            )
        else:
            print(
                f"Backend (discover_unreal_projects): {len(found_projects)} projetos encontrados. Enviando para UI."
            )
            app_instance.after(
                0,
                app_instance.update_project_list_ui_from_discovery,
                found_projects,
                None,
            )  # Passa a lista de dicionários de projetos

    except Exception as e:
        error_message = f"Erro excepcional ao procurar projetos em {base_path}: {e}"
        print(f"Backend (discover_unreal_projects): {error_message}")
        import traceback

        traceback.print_exc()  # Imprime o traceback completo no console para depuração
        app_instance.after(
            0, app_instance.update_project_list_ui_from_discovery, [], error_message
        )


def get_folder_size(folder_path):
    """Calcula o tamanho total de uma pasta e seu conteúdo em bytes."""
    total_size = 0
    if not os.path.exists(folder_path):
        return 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                try:
                    total_size += os.path.getsize(fp)
                except FileNotFoundError:
                    print(
                        f"Aviso: Arquivo não encontrado durante cálculo de tamanho: {fp}"
                    )
                    pass  # Arquivo pode ter sido deletado durante o walk
    return total_size


def format_size(size_bytes):
    """Converte bytes para um formato legível (KB, MB, GB)."""
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


# Cache folders a serem consideradas (relativo à pasta raiz do projeto)
# Vamos começar com estes, que são geralmente os maiores e mais seguros para limpar
CACHE_SUBFOLDERS_TO_SCAN = ["Intermediate", "DerivedDataCache"]
# Pastas 'Saved' são mais sensíveis. Poderíamos adicionar "Saved/Logs", "Saved/Crashes"
# mas é bom ter cuidado com "Saved/Config" ou "Saved/SaveGames"
# CACHE_SUBFOLDERS_TO_CLEAN = ["Intermediate", "DerivedDataCache", "Saved/Logs", "Saved/Crashes"]
CACHE_SUBFOLDERS_TO_CLEAN = ["Intermediate", "DerivedDataCache"]


def calculate_project_cache_size(project_path, selected_cleanup_items, app_instance):
    """
    Calcula o tamanho total dos itens de cache selecionados para um projeto.
    'selected_cleanup_items' é uma lista de strings:
        - Nomes de pastas principais (ex: "Saved") para contar arquivos soltos.
        - Caminhos relativos normalizados de subpastas (ex: os.path.normpath("Saved/Logs")).
    """
    total_cache_size = 0
    app_instance.log_message(
        f"CALC_SIZE: Iniciando cálculo de cache para '{project_path}' com itens selecionados: {selected_cleanup_items}",
        level="DEBUG",
    )

    processed_main_folders_for_loose_files = (
        set()
    )  # Para não contar arquivos soltos duas vezes se "Saved" e "Saved/Logs" estiverem implicitamente relacionados

    for item_id in selected_cleanup_items:
        item_path_abs = os.path.join(project_path, item_id)  # Monta o caminho completo

        # Verifica se o item_id é um nome de pasta principal (para arquivos soltos)
        # ou um caminho de subpasta.
        # Uma forma de distinguir: item_id não contém separador de diretório se for pasta principal.
        is_main_folder_for_loose_files = os.sep not in item_id and item_id in [
            "Intermediate",
            "DerivedDataCache",
            "Saved",
        ]

        if is_main_folder_for_loose_files:
            if item_id in processed_main_folders_for_loose_files:
                continue  # Já processamos os arquivos soltos desta pasta principal

            app_instance.log_message(
                f"CALC_SIZE: Calculando tamanho de arquivos soltos em '{item_path_abs}'...",
                level="TRACE",
            )
            if os.path.exists(item_path_abs) and os.path.isdir(item_path_abs):
                size_loose_files = 0
                try:
                    for entry in os.listdir(item_path_abs):
                        entry_abs_path = os.path.join(item_path_abs, entry)
                        if os.path.isfile(entry_abs_path) and not os.path.islink(
                            entry_abs_path
                        ):
                            try:
                                size_loose_files += os.path.getsize(entry_abs_path)
                            except FileNotFoundError:
                                app_instance.log_message(
                                    f"CALC_SIZE: Arquivo solto não encontrado durante cálculo: {entry_abs_path}",
                                    level="WARNING",
                                )
                    app_instance.log_message(
                        f"CALC_SIZE: Tamanho de arquivos soltos em '{item_id}': {format_size(size_loose_files)}",
                        level="DEBUG",
                    )
                    total_cache_size += size_loose_files
                    processed_main_folders_for_loose_files.add(item_id)
                except Exception as e_list_loose:
                    app_instance.log_message(
                        f"CALC_SIZE: Erro ao listar arquivos soltos em '{item_path_abs}': {e_list_loose}",
                        level="ERROR",
                    )
            else:
                app_instance.log_message(
                    f"CALC_SIZE: Pasta principal '{item_path_abs}' não encontrada para cálculo de arquivos soltos.",
                    level="WARNING",
                )

        else:  # É um caminho de subpasta
            app_instance.log_message(
                f"CALC_SIZE: Calculando tamanho da subpasta '{item_path_abs}'...",
                level="TRACE",
            )
            if os.path.exists(item_path_abs) and os.path.isdir(item_path_abs):
                size_subfolder = get_folder_size(
                    item_path_abs
                )  # get_folder_size já existe e calcula recursivamente
                app_instance.log_message(
                    f"CALC_SIZE: Tamanho de '{item_id}': {format_size(size_subfolder)}",
                    level="DEBUG",
                )
                total_cache_size += size_subfolder
            else:
                app_instance.log_message(
                    f"CALC_SIZE: Subpasta '{item_path_abs}' não encontrada para cálculo.",
                    level="WARNING",
                )

    app_instance.log_message(
        f"CALC_SIZE: Tamanho total do cache selecionado para '{project_path}': {format_size(total_cache_size)}",
        level="INFO",
    )
    return total_cache_size


def clean_project_cache(project_path, app_instance, selected_cleanup_items):
    """
    Deleta os itens de cache selecionados para um projeto, incluindo arquivos soltos
    nas pastas principais se suas subpastas forem limpas ou se a própria pasta principal
    for selecionada para limpeza de arquivos soltos.

    'selected_cleanup_items' é uma lista de strings:
        - Nomes de pastas principais (ex: "Saved") para limpar arquivos soltos.
        - Caminhos relativos normalizados de subpastas (ex: os.path.normpath("Saved/Logs")).
    Retorna: space_freed_total, successfully_deleted_relative_subfolder_paths, errors
    """
    space_freed_total = 0
    successfully_deleted_relative_subfolder_paths = []
    # Conjunto para rastrear pastas principais cujos arquivos soltos devem ser limpos
    # (seja por seleção direta da pasta principal ou por limpeza de uma de suas subpastas)
    main_folders_to_clean_loose_files = set()
    errors = []

    app_instance.log_message(
        f"CLEAN_BACKEND: Iniciando limpeza para '{project_path}' com itens selecionados: {selected_cleanup_items}",
        level="INFO",
    )

    # Passo 1: Deletar subpastas selecionadas e registrar suas pastas principais
    subfolder_ids_to_delete = [
        item for item in selected_cleanup_items if os.sep in item or "/" in item
    ]

    for relative_subfolder_path in subfolder_ids_to_delete:
        abs_subfolder_path = os.path.join(project_path, relative_subfolder_path)
        app_instance.log_message(
            f"CLEAN_BACKEND: Verificando subpasta para limpeza: {abs_subfolder_path}",
            level="DEBUG",
        )

        if os.path.exists(abs_subfolder_path) and os.path.isdir(abs_subfolder_path):
            app_instance.log_message(
                f"CLEAN_BACKEND: Tentando deletar subpasta {abs_subfolder_path}...",
                level="INFO",
            )
            try:
                folder_size_before_delete = get_folder_size(abs_subfolder_path)
                shutil.rmtree(abs_subfolder_path)

                if not os.path.exists(abs_subfolder_path):  # Confirma que foi deletado
                    app_instance.log_message(
                        f"CLEAN_BACKEND: Deletada com sucesso subpasta: {abs_subfolder_path}",
                        level="SUCCESS",
                    )
                    space_freed_total += folder_size_before_delete
                    successfully_deleted_relative_subfolder_paths.append(
                        relative_subfolder_path
                    )

                    # Adiciona a pasta pai (Saved, Intermediate, etc.) ao conjunto para limpeza de arquivos soltos
                    # Pega o primeiro componente do caminho relativo (ex: "Saved" de "Saved/Logs")
                    parent_folder_name = relative_subfolder_path.split(os.sep)[0]
                    if parent_folder_name in [
                        "Intermediate",
                        "DerivedDataCache",
                        "Saved",
                    ]:
                        main_folders_to_clean_loose_files.add(parent_folder_name)
                        app_instance.log_message(
                            f"CLEAN_BACKEND: Pasta principal '{parent_folder_name}' marcada para limpeza de arquivos soltos devido à deleção de subpasta.",
                            level="TRACE",
                        )
                else:
                    app_instance.log_message(
                        f"CLEAN_BACKEND: Subpasta {abs_subfolder_path} ainda existe após tentativa de rmtree.",
                        level="WARNING",
                    )
                    errors.append(f"Falha ao confirmar deleção de {abs_subfolder_path}")
            except OSError as e:
                error_msg = (
                    f"CLEAN_BACKEND: Erro ao deletar subpasta {abs_subfolder_path}: {e}"
                )
                app_instance.log_message(error_msg, level="ERROR")
                errors.append(error_msg)
        else:
            app_instance.log_message(
                f"CLEAN_BACKEND: Subpasta '{relative_subfolder_path}' não encontrada ou não é diretório em '{project_path}'.",
                level="WARNING",
            )

    # Passo 2: Adicionar pastas principais que foram explicitamente selecionadas para limpeza de arquivos soltos
    explicitly_selected_main_folder_ids = [
        item
        for item in selected_cleanup_items
        if (os.sep not in item and "/" not in item)
        and item in ["Intermediate", "DerivedDataCache", "Saved"]
    ]
    for main_folder_name in explicitly_selected_main_folder_ids:
        main_folders_to_clean_loose_files.add(main_folder_name)
        app_instance.log_message(
            f"CLEAN_BACKEND: Pasta principal '{main_folder_name}' explicitamente selecionada para limpeza de arquivos soltos.",
            level="TRACE",
        )

    # Passo 3: Deletar arquivos soltos das pastas principais identificadas
    cleaned_loose_files_summary = (
        []
    )  # Para logar quais pastas tiveram arquivos soltos limpos

    for main_folder_name in main_folders_to_clean_loose_files:
        abs_main_folder_path = os.path.join(project_path, main_folder_name)
        app_instance.log_message(
            f"CLEAN_BACKEND: Verificando arquivos soltos para limpeza em: {abs_main_folder_path}",
            level="DEBUG",
        )

        if os.path.exists(abs_main_folder_path) and os.path.isdir(abs_main_folder_path):
            files_deleted_count_in_main = 0
            space_freed_this_main_loose = 0
            try:
                for item_name in os.listdir(abs_main_folder_path):
                    item_abs_path = os.path.join(abs_main_folder_path, item_name)
                    if os.path.isfile(item_abs_path) and not os.path.islink(
                        item_abs_path
                    ):
                        app_instance.log_message(
                            f"CLEAN_BACKEND: Tentando deletar arquivo solto: {item_abs_path}",
                            level="TRACE",
                        )
                        try:
                            file_size = os.path.getsize(item_abs_path)
                            os.remove(item_abs_path)
                            space_freed_total += file_size  # Adiciona ao total geral
                            space_freed_this_main_loose += file_size
                            files_deleted_count_in_main += 1
                        except Exception as e_file_del:
                            error_msg_file = f"CLEAN_BACKEND: Erro ao deletar arquivo solto {item_abs_path}: {e_file_del}"
                            app_instance.log_message(error_msg_file, level="ERROR")
                            errors.append(error_msg_file)

                if files_deleted_count_in_main > 0:
                    log_msg_loose = f"Deletados {files_deleted_count_in_main} arquivos soltos de '{main_folder_name}', liberando {format_size(space_freed_this_main_loose)}."
                    app_instance.log_message(
                        f"CLEAN_BACKEND: {log_msg_loose}", level="SUCCESS"
                    )
                    cleaned_loose_files_summary.append(
                        f"{main_folder_name} ({format_size(space_freed_this_main_loose)})"
                    )
                else:
                    app_instance.log_message(
                        f"CLEAN_BACKEND: Nenhum arquivo solto encontrado ou deletado em '{main_folder_name}'.",
                        level="DEBUG",
                    )

            except Exception as e_list_main:
                error_msg_list = f"CLEAN_BACKEND: Erro ao listar arquivos em {abs_main_folder_path} para limpeza de arquivos soltos: {e_list_main}"
                app_instance.log_message(error_msg_list, level="ERROR")
                errors.append(error_msg_list)
        else:
            app_instance.log_message(
                f"CLEAN_BACKEND: Pasta principal '{main_folder_name}' não encontrada para verificar arquivos soltos.",
                level="WARNING",
            )

    # Monta a lista final de itens limpos para o log (subpastas + indicação de arquivos soltos)
    final_cleaned_items_summary = successfully_deleted_relative_subfolder_paths[
        :
    ]  # Cria uma cópia
    if cleaned_loose_files_summary:
        final_cleaned_items_summary.append(
            f"Arquivos soltos de: {', '.join(cleaned_loose_files_summary)}"
        )

    app_instance.log_message(
        f"CLEAN_BACKEND: Limpeza concluída para '{project_path}'. Total liberado: {format_size(space_freed_total)}. Itens afetados: {final_cleaned_items_summary if final_cleaned_items_summary else 'Nenhum'}. Erros: {len(errors)}",
        level="INFO",
    )

    # Retorna os caminhos das SUBPASTAS que foram deletadas (para atualização da UI)
    return space_freed_total, successfully_deleted_relative_subfolder_paths, errors


def find_uproject_file(project_root_path):
    """Encontra o primeiro arquivo .uproject na raiz de um projeto."""
    if not os.path.isdir(project_root_path):
        return None
    for item_name in os.listdir(project_root_path):
        if item_name.endswith(".uproject"):
            return os.path.join(project_root_path, item_name)
    return None


def is_unreal_project_open(project_root_path):
    """
    Verifica se um projeto Unreal específico está aberto em algum editor.
    project_root_path: O caminho para a pasta raiz do projeto.
    """
    uproject_file_path = find_uproject_file(project_root_path)
    if not uproject_file_path:
        print(f"Backend (is_open): .uproject não encontrado em {project_root_path}")
        return False  # Não pode determinar se não achar o .uproject

    # Normaliza o caminho do arquivo .uproject para comparação confiável
    normalized_uproject_path = os.path.normpath(uproject_file_path)

    editor_executables = ["UE4Editor.exe", "UE5Editor.exe", "UnrealEditor.exe"]
    # Adicionar variantes como "UnrealEditor-Win64-Development.exe" se necessário

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            proc_name = proc.info["name"]
            cmdline = proc.info["cmdline"]

            if proc_name in editor_executables and cmdline:
                # cmdline pode ser None ou vazio para alguns processos do sistema
                # O primeiro argumento geralmente é o executável, o segundo pode ser o projeto
                for arg in cmdline:
                    # Normaliza o argumento para comparação
                    normalized_arg_path = os.path.normpath(
                        arg.strip('"')
                    )  # Remove aspas se houver
                    if normalized_arg_path == normalized_uproject_path:
                        print(
                            f"Backend (is_open): Projeto {uproject_file_path} está ABERTO (Processo: {proc_name}, PID: {proc.info['pid']})"
                        )
                        return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass  # Processo pode ter terminado ou acesso negado, ignora

    print(f"Backend (is_open): Projeto {uproject_file_path} está FECHADO.")
    return False


def resource_path(relative_path):
    """Retorna o caminho absoluto para o recurso, funciona para dev e para PyInstaller"""
    try:
        # PyInstaller cria uma pasta temp e armazena o caminho em _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # base_path será o diretório onde o script está localizado em modo de desenvolvimento
        base_path = os.path.abspath(os.path.dirname(__file__))  # Mais robusto para dev
        # Se preferir o diretório de trabalho atual em dev (CWD):
        # base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# --- Interface Gráfica (CustomTkinter) ---


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Limpador de Cache Unreal Engine")
        self.geometry("1070x800")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # --- DEFINIR ÍCONE DA JANELA PRINCIPAL ---
        try:
            icon_path = resource_path(
                "CleanUnreal.ico"
            )  # Usa a função para obter o caminho
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)  # Define o ícone da janela
                self.log_message(
                    f"Ícone da janela principal '{icon_path}' carregado.", level="DEBUG"
                )
            else:
                self.log_message(
                    f"AVISO: Ícone da janela principal '{icon_path}' NÃO ENCONTRADO.",
                    level="WARNING",
                )
        except Exception as e:
            self.log_message(
                f"Erro ao definir o ícone da janela principal: {e}", level="ERROR"
            )
        # -----------------------------------------

        # --- CRIA O TABVIEW COMO ELEMENTO PRINCIPAL ---
        self.tab_view = ctk.CTkTabview(self, corner_radius=8)
        self.tab_view.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_view.add("Gerenciador")  # Nome da primeira aba
        self.tab_view.add("Logs")  # Nome da segunda aba

        # --- FRAME PRINCIPAL DA ABA "GERENCIADOR" ---
        # Todo o conteúdo que antes estava em self.main_frame agora vai para self.tab_view.tab("Gerenciador")
        self.manager_tab_frame = self.tab_view.tab("Gerenciador")

        # --- Frame de Controles Globais (dentro da aba "Gerenciador") ---
        self.global_actions_frame = ctk.CTkFrame(
            self.manager_tab_frame
        )  # Pai agora é manager_tab_frame
        self.global_actions_frame.pack(fill="x", pady=(0, 10))
        # ... (seus botões analyze_all_button, clean_allowed_button, global_status_label como antes, mas com pai global_actions_frame) ...
        self.analyze_all_button = ctk.CTkButton(
            self.global_actions_frame,
            text="Analisar Todos os Projetos",
            command=self.analyze_all_projects_action,
        )
        self.analyze_all_button.pack(side="left", padx=5, pady=5)

        self.clean_allowed_button = ctk.CTkButton(
            self.global_actions_frame,
            text="Limpar Projetos Permitidos",
            command=self.clean_allowed_projects_action,
        )
        self.clean_allowed_button.pack(side="left", padx=5, pady=5)

        self.global_status_label = ctk.CTkLabel(
            self.global_actions_frame, text="Status Global: Pronto"
        )
        self.global_status_label.pack(side="left", padx=10, pady=5)

        # --- Frame de Configurações de Monitoramento (Pai) ---
        self.monitoring_parent_frame = ctk.CTkFrame(self.manager_tab_frame)
        self.monitoring_parent_frame.pack(fill="x", pady=(0, 10))

        # --- Linha 1 dos Controles de Monitoramento ---
        self.monitoring_line1_frame = ctk.CTkFrame(self.monitoring_parent_frame)
        self.monitoring_line1_frame.pack(fill="x")

        self.auto_start_monitoring_checkbox = ctk.CTkCheckBox(
            self.monitoring_line1_frame,  # Adiciona à primeira linha
            text="Ativar monitoramento automático ao iniciar o programa",
        )
        self.auto_start_monitoring_checkbox.pack(side="left", padx=5, pady=5)

        self.start_with_windows_checkbox = ctk.CTkCheckBox(
            self.monitoring_line1_frame,  # Adiciona à primeira linha
            text="Iniciar com o Windows",
            command=self.toggle_startup_status,
        )
        self.start_with_windows_checkbox.pack(side="left", padx=(10, 5), pady=5)

        self.monitoring_interval_label = ctk.CTkLabel(
            self.monitoring_line1_frame,  # Adiciona à primeira linha
            text="Intervalo (minutos):",
        )
        self.monitoring_interval_label.pack(side="left", padx=(10, 2), pady=5)

        self.monitoring_interval_var = ctk.StringVar()
        self.monitoring_interval_var.trace_add(
            "write", self.on_monitoring_interval_change
        )
        self.monitoring_interval_entry = ctk.CTkEntry(
            self.monitoring_line1_frame,  # Adiciona à primeira linha
            width=60,
            textvariable=self.monitoring_interval_var,
            placeholder_text="Ex: 60",
        )
        self.monitoring_interval_entry.pack(side="left", padx=(0, 10), pady=5)

        # --- Linha 2 dos Controles de Monitoramento ---
        self.monitoring_line2_frame = ctk.CTkFrame(self.monitoring_parent_frame)
        self.monitoring_line2_frame.pack(
            fill="x", pady=(5, 0)
        )  # Um pouco de pady entre as linhas

        self.start_monitoring_button_ui = ctk.CTkButton(
            self.monitoring_line2_frame,  # Adiciona à segunda linha
            text="Iniciar Monitoramento",
            command=self.start_auto_monitoring,
            width=150,
        )
        self.start_monitoring_button_ui.pack(side="left", padx=5, pady=5)

        self.stop_monitoring_button_ui = ctk.CTkButton(
            self.monitoring_line2_frame,  # Adiciona à segunda linha
            text="Parar Monitoramento",
            command=self.stop_auto_monitoring,
            state="disabled",
            width=150,
        )
        self.stop_monitoring_button_ui.pack(side="left", padx=5, pady=5)

        self.monitoring_status_label = ctk.CTkLabel(
            self.monitoring_line2_frame,  # Adiciona à segunda linha
            text="Monitoramento Automático: Parado",
        )
        # Para o label de status, se você quiser que ele use o espaço restante:
        self.monitoring_status_label.pack(
            side="left", padx=10, pady=5, fill="x", expand=True
        )

        # --- Seção da Lista de Projetos (dentro da aba "Gerenciador") ---
        self.project_list_title_label = ctk.CTkLabel(
            self.manager_tab_frame,
            text="Projetos:",
            font=ctk.CTkFont(size=16, weight="bold"),
        )  # Pai agora é manager_tab_frame
        self.project_list_title_label.pack(fill="x", pady=(5, 5))

        self.project_scrollable_frame = ctk.CTkScrollableFrame(
            self.manager_tab_frame, height=350
        )  # Pai agora é manager_tab_frame
        self.project_scrollable_frame.pack(fill="both", expand=True)

        # --- Frame dos Botões de Scan/Add Manual (dentro da aba "Gerenciador") ---
        self.discovery_controls_frame = ctk.CTkFrame(
            self.manager_tab_frame
        )  # Pai agora é manager_tab_frame
        self.discovery_controls_frame.pack(fill="x", pady=(10, 0))
        # ... (seus botões scan_default_button e manual_add_button como antes) ...
        self.scan_default_button = ctk.CTkButton(
            self.discovery_controls_frame,
            text="Escanear Pasta Padrão Novamente",
            command=lambda: self.start_discover_projects_thread(
                clear_current_list=True
            ),
        )
        self.scan_default_button.pack(side="left", padx=5, pady=5)

        self.manual_add_button = ctk.CTkButton(
            self.discovery_controls_frame,
            text="Adicionar Projeto Manualmente",
            command=self.prompt_add_project_manually,
        )
        self.manual_add_button.pack(side="left", padx=5, pady=5)

        # --- Configuração da Aba de Logs ---
        self.log_tab_frame = self.tab_view.tab("Logs")
        self.log_textbox = ctk.CTkTextbox(
            self.log_tab_frame,
            wrap="word",  # Quebra de linha por palavra
            state="disabled",  # Começa desabilitado para edição pelo usuário
            font=("Consolas", 10),  # Fonte monoespaçada para logs
        )
        self.log_textbox.pack(fill="both", expand=True, padx=5, pady=5)

        # Atributos da classe (como antes)
        self.project_widgets = []
        self.displayed_project_paths = set()
        self.monitoring_thread = None
        self.monitoring_stop_event = threading.Event()
        self.AUTO_MONITOR_INTERVAL_SECONDS = 3600

        self.tray_icon = None
        self.icon_image = None
        self.is_window_visible = True

        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.after(100, self.setup_and_run_tray_icon)

        # Carregar dados e iniciar automaticamente
        self.log_message("Aplicativo iniciando...")  # Exemplo de uso do novo logger
        self.load_app_data()
        self.initial_project_discovery_and_load()

        if self.auto_start_monitoring_checkbox.get() == 1:
            self.start_auto_monitoring()

        if sys.platform == "win32":  # Só faz sentido no Windows
            self._check_startup_status()
        # ...

        self.log_message("Interface principal inicializada.")

        # Inicia o monitoramento se configurado (como antes)
        if self.auto_start_monitoring_checkbox.get() == 1:
            self.start_auto_monitoring()

        if self.auto_start_monitoring_checkbox.get() == 1:
            self.start_auto_monitoring()  # Isso já vai configurar os botões e o label
        else:
            # Garante estado inicial correto dos botões se não iniciar automaticamente
            if hasattr(self, "start_monitoring_button_ui"):
                self.start_monitoring_button_ui.configure(state="normal")
            if hasattr(self, "stop_monitoring_button_ui"):
                self.stop_monitoring_button_ui.configure(state="disabled")
            if hasattr(self, "monitoring_status_label"):
                self.monitoring_status_label.configure(
                    text="Monitoramento Automático: Parado"
                )

        # Opcional: Iniciar minimizado (pode ser uma configuração no futuro)
        # if self.settings.get("start_minimized_to_tray", False): # Exemplo
        #     self.hide_to_tray()

    def refresh_project_cleanup_items_ui(
        self, project_widget_info, successfully_deleted_relative_subfolder_paths
    ):
        """
        Remove da UI os widgets (checkboxes e seus frames) correspondentes às subpastas
        que foram deletadas do disco. Também atualiza o folder_checkboxes_map interno.
        """
        if not successfully_deleted_relative_subfolder_paths:
            self.log_message(
                f"REFRESH_UI: Nenhuma subpasta deletada reportada para o projeto '{project_widget_info['data']['name']}'. Nada a atualizar na UI.",
                level="DEBUG",
            )
            return

        project_name_for_log = project_widget_info.get("data", {}).get(
            "name", "Desconhecido_Refresh"
        )
        self.log_message(
            f"REFRESH_UI: Atualizando lista de subpastas para o projeto '{project_name_for_log}' após deleções: {successfully_deleted_relative_subfolder_paths}",
            level="INFO",
        )

        folder_checkboxes_map = project_widget_info.get("folder_checkboxes", {})

        # Precisamos de uma referência ao frame que contém todos os 'item_frame' das subpastas
        # para verificar se ele ficou vazio e, talvez, atualizar o botão de toggle.
        # Esta referência deve ser o 'selectable_items_frame_ui' da função add_project_entry_to_ui
        # para cada categoria (Intermediate, DerivedDataCache, Saved).
        # A estrutura atual de add_project_entry_to_ui cria um selectable_items_frame_ui GERAL
        # e dentro dele os cabeçalhos e depois os item_frames das subpastas.

        items_removed_from_map = []

        for rel_path_deleted_raw in successfully_deleted_relative_subfolder_paths:
            # Garante que estamos usando o mesmo formato de caminho normalizado que foi usado como chave no mapa
            normalized_rel_path_deleted = os.path.normpath(rel_path_deleted_raw)

            if normalized_rel_path_deleted in folder_checkboxes_map:
                chk_data = folder_checkboxes_map[normalized_rel_path_deleted]
                checkbox_widget = chk_data.get("widget")  # Este é o CTkCheckBox

                if (
                    checkbox_widget
                    and hasattr(checkbox_widget, "master")
                    and checkbox_widget.master
                ):
                    # O 'master' do CTkCheckBox é o 'item_frame' que contém o checkbox e o label de descrição.
                    item_frame_to_destroy = checkbox_widget.master

                    if (
                        hasattr(item_frame_to_destroy, "winfo_exists")
                        and item_frame_to_destroy.winfo_exists()
                    ):
                        item_frame_to_destroy.destroy()
                        self.log_message(
                            f"REFRESH_UI: Removido da UI o item de limpeza: {normalized_rel_path_deleted} para o projeto '{project_name_for_log}'.",
                            level="DEBUG",
                        )
                        items_removed_from_map.append(normalized_rel_path_deleted)
                    else:
                        self.log_message(
                            f"REFRESH_UI: Tentativa de destruir frame para '{normalized_rel_path_deleted}', mas o frame já não existe (projeto '{project_name_for_log}').",
                            level="TRACE",
                        )
                else:
                    self.log_message(
                        f"REFRESH_UI: Não foi possível encontrar o frame pai para o checkbox de '{normalized_rel_path_deleted}' (projeto '{project_name_for_log}').",
                        level="WARNING",
                    )

                # Remove do mapa na memória DEPOIS de tentar destruir o widget
                # Isso garante que mesmo que a destruição falhe por algum motivo, tentamos limpar o mapa.
                if (
                    normalized_rel_path_deleted in items_removed_from_map
                ):  # Só remove do mapa se a UI foi atualizada
                    del folder_checkboxes_map[normalized_rel_path_deleted]

            else:
                self.log_message(
                    f"REFRESH_UI: Subpasta deletada '{normalized_rel_path_deleted}' não encontrada no folder_checkboxes_map do projeto '{project_name_for_log}' para remoção da UI.",
                    level="TRACE",
                )

        # Após remover todos os itens deletados, podemos querer verificar se algum
        # 'main_folder_header_label' (ex: "Saved:") agora não tem mais nenhuma subpasta listada abaixo dele
        # e, se for o caso, adicionar uma mensagem "(Nenhuma subpasta encontrada)" e desabilitar o botão de toggle.
        # Esta parte é mais complexa e envolve re-verificar a estrutura da UI.
        # Por enquanto, o foco é remover os itens que foram deletados.

        # Força um redesenho da lista de projetos, se necessário (geralmente não é preciso com .destroy())
        # self.project_scrollable_frame.update_idletasks()

        self.log_message(
            f"REFRESH_UI: Concluída atualização da UI para '{project_name_for_log}'. Itens removidos do mapa: {items_removed_from_map}",
            level="DEBUG",
        )

    def toggle_visibility(
        self, frame_to_toggle, button_pressed, button_text_prefix="Subpastas"
    ):
        """Mostra ou esconde um frame e atualiza o texto do botão."""
        if frame_to_toggle.winfo_ismapped():  # Se o frame está visível
            frame_to_toggle.pack_forget()  # Esconde o frame
            if button_pressed:
                button_pressed.configure(
                    text=f"{button_text_prefix} ▼"
                )  # Texto para mostrar
        else:
            # Simplesmente faz o pack. O botão ficará acima do frame que é mostrado.
            frame_to_toggle.pack(
                fill="x", padx=5, pady=(0, 5), after=button_pressed.master
            )  # Tenta empacotar depois do frame do botão
            if button_pressed:
                button_pressed.configure(
                    text=f"{button_text_prefix} ▲"
                )  # Texto para recolher

    def on_monitoring_interval_change(
        self, *args
    ):  # *args é necessário para o callback do trace da StringVar
        """
        Chamado quando o valor do campo de entrada do intervalo de monitoramento (em minutos) muda.
        Valida a entrada, converte para segundos e atualiza self.AUTO_MONITOR_INTERVAL_SECONDS.
        """
        current_value_str_minutes = self.monitoring_interval_var.get()
        self.log_message(
            f"ON_INTERVAL_CHANGE: Valor digitado no campo de minutos: '{current_value_str_minutes}'",
            level="TRACE",
        )

        MIN_INPUT_INTERVAL_MINUTES = (
            1  # Define um valor mínimo que o usuário pode configurar na UI (em minutos)
        )

        # Calcula o valor de fallback EM MINUTOS a partir do AUTO_MONITOR_INTERVAL_SECONDS atual (que está em segundos)
        # Este valor será usado para reverter a UI em caso de entrada inválida.
        current_auto_interval_in_minutes = self.AUTO_MONITOR_INTERVAL_SECONDS // 60
        if current_auto_interval_in_minutes < MIN_INPUT_INTERVAL_MINUTES:
            # Se o valor interno atual for menor que o mínimo permitido na UI (ex: após carregar um valor inválido),
            # o fallback para a UI deve ser o mínimo permitido na UI.
            fallback_minutes_str = str(MIN_INPUT_INTERVAL_MINUTES)
        else:
            fallback_minutes_str = str(current_auto_interval_in_minutes)

        try:
            if not current_value_str_minutes:
                self.log_message(
                    f"ON_INTERVAL_CHANGE: Campo de intervalo (minutos) esvaziado. Intervalo interno (segundos) permanece: {self.AUTO_MONITOR_INTERVAL_SECONDS}s",
                    level="DEBUG",
                )
                # Se o campo estiver vazio, não fazemos nada com AUTO_MONITOR_INTERVAL_SECONDS.
                # Opcionalmente, você poderia reverter para o fallback aqui também se preferir que o campo não fique vazio.
                # Ex: self.after(500, lambda: self.monitoring_interval_var.set(fallback_minutes_str) if not self.monitoring_interval_var.get() else None)
                return

            new_interval_minutes_int = int(current_value_str_minutes)

            if new_interval_minutes_int >= MIN_INPUT_INTERVAL_MINUTES:
                new_interval_seconds_int = new_interval_minutes_int * 60
                if self.AUTO_MONITOR_INTERVAL_SECONDS != new_interval_seconds_int:
                    self.AUTO_MONITOR_INTERVAL_SECONDS = new_interval_seconds_int
                    self.log_message(
                        f"ON_INTERVAL_CHANGE: Intervalo de monitoramento (interno) atualizado para: {self.AUTO_MONITOR_INTERVAL_SECONDS} segundos ({new_interval_minutes_int} minutos).",
                        level="INFO",
                    )
                else:
                    self.log_message(
                        f"ON_INTERVAL_CHANGE: Valor do intervalo (minutos) '{new_interval_minutes_int}' resultou no mesmo intervalo em segundos ({self.AUTO_MONITOR_INTERVAL_SECONDS}s). Nenhuma mudança interna.",
                        level="TRACE",
                    )
            else:
                self.log_message(
                    f"ON_INTERVAL_CHANGE: Tentativa de definir intervalo menor que {MIN_INPUT_INTERVAL_MINUTES} min ('{current_value_str_minutes}'). Intervalo interno (segundos) mantido em: {self.AUTO_MONITOR_INTERVAL_SECONDS}s.",
                    level="WARNING",
                )
                # Reverte o campo da UI para o valor de fallback após um pequeno delay
                # para permitir que o usuário termine de digitar ou corrija.
                self.after(
                    1500,
                    lambda: (
                        self.monitoring_interval_var.set(fallback_minutes_str)
                        if self.monitoring_interval_var.get()
                        == current_value_str_minutes
                        else None
                    ),
                )

        except ValueError:
            if (
                current_value_str_minutes
            ):  # Só loga e tenta reverter se não for string vazia
                self.log_message(
                    f"ON_INTERVAL_CHANGE: Valor de intervalo (minutos) não numérico digitado: '{current_value_str_minutes}'. Intervalo interno (segundos) mantido em: {self.AUTO_MONITOR_INTERVAL_SECONDS}s.",
                    level="WARNING",
                )
                # Reverte o campo da UI para o valor de fallback
                self.after(
                    1500,
                    lambda: (
                        self.monitoring_interval_var.set(fallback_minutes_str)
                        if self.monitoring_interval_var.get()
                        == current_value_str_minutes
                        else None
                    ),
                )

    def _get_executable_path(self):
        """Retorna o caminho do executável atual."""
        if hasattr(sys, "frozen") and sys.frozen:  # Rodando como .exe (PyInstaller)
            return sys.executable
        else:  # Rodando como script .py
            return os.path.abspath(__file__)  # Ou sys.argv[0]

    def _set_startup_registry(self, app_name, exe_path, enable=True):
        """Adiciona ou remove a aplicação da inicialização do Windows via Registro."""
        if sys.platform != "win32":
            self.log_message(
                "Configuração de inicializar com o sistema operacional só é suportada no Windows.",
                level="WARNING",
            )
            return False

        registry_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, registry_key_path, 0, winreg.KEY_WRITE
            )
            if enable:
                winreg.SetValueEx(
                    key, app_name, 0, winreg.REG_SZ, f'"{exe_path}"'
                )  # Adiciona aspas para caminhos com espaços
                self.log_message(
                    f"'{app_name}' adicionado à inicialização do Windows.", level="INFO"
                )
            else:
                winreg.DeleteValue(key, app_name)
                self.log_message(
                    f"'{app_name}' removido da inicialização do Windows.", level="INFO"
                )
            winreg.CloseKey(key)
            return True
        except (
            FileNotFoundError
        ):  # A chave pode não existir se o programa nunca foi adicionado
            if not enable:  # Se estamos tentando remover e não existe, está ok
                self.log_message(
                    f"'{app_name}' não encontrado na inicialização do Windows para remover.",
                    level="INFO",
                )
                return True
            self.log_message(
                f"Erro: Chave do Registro não encontrada para '{app_name}' ao tentar remover.",
                level="ERROR",
            )
            return False
        except Exception as e:
            self.log_message(
                f"Erro ao {'adicionar' if enable else 'remover'} '{app_name}' {'à' if enable else 'da'} inicialização do Windows: {e}",
                level="ERROR",
            )
            import traceback

            traceback.print_exc()  # Para mais detalhes do erro no console
            return False

    def toggle_startup_status(self):
        """Chamado quando o checkbox 'Iniciar com o Windows' é alterado."""
        app_name = (
            "LimpadorUnrealCache"  # Nome que aparecerá no gerenciador de inicialização
        )
        exe_path = self._get_executable_path()

        if self.start_with_windows_checkbox.get() == 1:  # Se está marcado
            self._set_startup_registry(app_name, exe_path, enable=True)
        else:  # Se está desmarcado
            self._set_startup_registry(app_name, exe_path, enable=False)

        # Salva o estado do checkbox imediatamente (ou você pode esperar o save_app_data geral)
        self.save_app_data()  # Para persistir a configuração do checkbox

    def _check_startup_status(self):
        """Verifica se a aplicação está configurada para iniciar com o Windows e atualiza o checkbox."""
        if sys.platform != "win32":
            return

        app_name = "LimpadorUnrealCache"
        registry_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        is_in_startup = False
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, registry_key_path, 0, winreg.KEY_READ
            )
            winreg.QueryValueEx(
                key, app_name
            )  # Tenta ler o valor; se não existir, lança FileNotFoundError
            is_in_startup = True
            winreg.CloseKey(key)
        except FileNotFoundError:
            is_in_startup = False
        except Exception as e:
            self.log_message(
                f"Erro ao verificar status de inicialização com Windows: {e}",
                level="WARNING",
            )
            is_in_startup = False  # Assume que não está no startup em caso de erro

        if is_in_startup:
            self.start_with_windows_checkbox.select()
        else:
            self.start_with_windows_checkbox.deselect()
        self.log_message(
            f"Checkbox 'Iniciar com Windows' atualizado para: {'Selecionado' if is_in_startup else 'Não Selecionado'}",
            level="DEBUG",
        )

    def _add_text_to_log_textbox(self, text_to_add):
        print(
            f"--- DEBUG (_add_text_to_log_textbox): Tentando adicionar: {text_to_add.strip()} ---"
        )

        try:
            if (
                hasattr(self, "log_textbox") and self.log_textbox.winfo_exists()
            ):  # Verifica se o widget ainda existe
                self.log_textbox.configure(state="normal")
                self.log_textbox.insert("end", text_to_add)
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")
                print(
                    f"--- DEBUG (_add_text_to_log_textbox): Texto adicionado à UI. ---"
                )
            else:
                print(
                    f"--- DEBUG (_add_text_to_log_textbox): ERRO - log_textbox não existe ou foi destruído. ---"
                )
        except Exception as e:
            print(
                f"--- DEBUG (_add_text_to_log_textbox): ERRO CRÍTICO ao adicionar texto: {e} ---"
            )
            import traceback

            traceback.print_exc()

    def log_message(self, message, level="INFO"):
        print(
            f"--- DEBUG (log_message): Chamada para log_message com: '{message}' ---"
        )  # Print de depuração
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entry_console = f"CONSOLE LOG: [{timestamp}] [{level}] {message}"
        log_entry_ui = f"[{timestamp}] [{level}] {message}\n"

        print(log_entry_console.strip())

        if hasattr(self, "log_textbox") and self.log_textbox.winfo_exists():
            print(
                f"--- DEBUG (log_message): log_textbox existe. Agendando _add_text_to_log_textbox. ---"
            )
            self.after(0, self._add_text_to_log_textbox, log_entry_ui)
        else:
            print(
                f"--- DEBUG (log_message): log_textbox NÃO existe ou foi destruído. Mensagem não irá para UI. ---"
            )

    def setup_and_run_tray_icon(self):
        print("--- DEBUG: setup_and_run_tray_icon INICIADA ---")

        self.icon_image = None  # Inicializa
        try:
            icon_path = resource_path("CleanUnreal.ico")
            if os.path.exists(icon_path):
                self.icon_image = Image.open(icon_path)
                print(f"UI: Ícone '{icon_path}' carregado com sucesso para a bandeja.")
            else:
                print(f"AVISO CRÍTICO: Arquivo de ícone '{icon_path}' NÃO ENCONTRADO.")
        except Exception as e_icon_load:
            print(
                f"Erro CRÍTICO ao carregar imagem do ícone '{icon_path}': {e_icon_load}"
            )
            import traceback

            traceback.print_exc()

        try:
            print("--- DEBUG: setup_and_run_tray_icon - Tentando criar menu_items ---")
            # Chama create_monitoring_submenu que agora também tem try-except
            monitoring_submenu_items = self.create_monitoring_submenu()

            menu_items = (
                pystray.MenuItem("Abrir Limpador", self.show_from_tray, default=True),
                pystray.MenuItem("Monitoramento", monitoring_submenu_items),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Fechar Limpador", self.quit_from_tray_menu),
            )
            print(
                "--- DEBUG: setup_and_run_tray_icon - menu_items criados com sucesso ---"
            )

            self.tray_icon = pystray.Icon(
                "LimpadorUnreal",
                icon=self.icon_image,
                title="Limpador de Cache Unreal",
                menu=menu_items,
            )
            print(
                "--- DEBUG: setup_and_run_tray_icon - pystray.Icon criado com sucesso ---"
            )

            self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self.tray_thread.start()
            print("--- DEBUG: setup_and_run_tray_icon - Thread da bandeja iniciada ---")

            if self.icon_image:
                print(
                    "UI: Ícone da bandeja configurado e thread iniciada (com imagem)."
                )
            else:
                print(
                    "UI: Configuração da bandeja concluída (sem imagem ou com erro no carregamento da imagem)."
                )

        except Exception as e_tray_setup:
            print(
                f"--- DEBUG: ERRO CRÍTICO em setup_and_run_tray_icon durante a configuração do pystray: {e_tray_setup} ---"
            )
            import traceback

            traceback.print_exc()
            self.tray_icon = None

    def get_tray_monitoring_status_text(
        self, item=None
    ):  # <--- ADICIONE item=None AQUI
        # Use print direto para depuração aqui, pois self.log_message pode ser o problema
        print("--- DEBUG: get_tray_monitoring_status_text FOI CHAMADA ---")
        # O argumento 'item' é o objeto pystray.MenuItem, você pode ignorá-lo se não precisar dele.
        try:
            is_alive_now = self.monitoring_thread and self.monitoring_thread.is_alive()
            status_text = f"Status: {'Ativo' if is_alive_now else 'Parado'}"
            print(
                f"--- DEBUG: get_tray_monitoring_status_text retornando: '{status_text}' ---"
            )
            return status_text
        except Exception as e:
            print(f"--- DEBUG: ERRO dentro de get_tray_monitoring_status_text: {e} ---")
            import traceback

            traceback.print_exc()
            return "Status: Erro"

    def create_monitoring_submenu(self):
        print("--- DEBUG: create_monitoring_submenu FOI CHAMADA ---")
        try:
            menu = pystray.Menu(
                pystray.MenuItem(
                    "Alternar Monitoramento", self.toggle_monitoring_from_tray
                ),
                pystray.MenuItem(
                    self.get_tray_monitoring_status_text,  # Chama o método
                    action=None,
                    enabled=False,
                ),
            )
            print("--- DEBUG: create_monitoring_submenu - Menu criado com sucesso ---")
            return menu
        except Exception as e:
            print(f"--- DEBUG: ERRO CRÍTICO em create_monitoring_submenu: {e} ---")
            import traceback

            traceback.print_exc()
            # Retorna um menu mínimo em caso de erro para tentar manter o ícone principal funcionando
            return pystray.Menu(pystray.MenuItem("Erro no submenu", None))

    def toggle_monitoring_from_tray(self):
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            print("Tray: Comandado Parar Monitoramento")
            # Agendando para a thread principal da UI para segurança
            self.after(0, self.stop_auto_monitoring)
        else:
            print("Tray: Comandado Iniciar Monitoramento")
            # Agendando para a thread principal da UI para segurança
            self.after(0, self.start_auto_monitoring)
        # Atualizar o menu da bandeja para refletir o novo estado é mais complexo com pystray
        # sem recriar o ícone ou usar truques. O submenu lambda acima ajuda um pouco.

    def hide_to_tray(self):
        """Esconde a janela principal e mostra o ícone na bandeja (se não já estiver)."""
        print("UI: Minimizando para a bandeja...")
        self.withdraw()  # Esconde a janela principal
        self.is_window_visible = False
        # O ícone da bandeja já deve estar rodando pela chamada em __init__

    def show_from_tray(self):
        """Mostra a janela principal a partir da bandeja."""
        print("UI: Restaurando da bandeja...")
        self.deiconify()  # Reexibe a janela
        self.lift()  # Traz para frente
        self.focus_force()  # Tenta focar
        self.is_window_visible = True

    def quit_application(self):  # Esta função é chamada pelo menu da bandeja "Fechar"
        print("--- DEBUG: quit_application() INICIADA ---")

        print("--- DEBUG: quit_application() - Chamando on_closing_logic()... ---")
        self.on_closing_logic()
        print("--- DEBUG: quit_application() - on_closing_logic() CONCLUÍDA. ---")

        if self.tray_icon:
            print(
                "--- DEBUG: quit_application() - Parando ícone da bandeja (chamando self.tray_icon.stop())... ---"
            )
            self.tray_icon.stop()  # Apenas sinaliza para a thread do pystray parar.
            # NENHUM self.tray_thread.join() AQUI!
            print(
                "--- DEBUG: quit_application() - self.tray_icon.stop() chamado. A thread da bandeja deve terminar por conta própria. ---"
            )
        else:
            print("--- DEBUG: quit_application() - Nenhum tray_icon para parar. ---")

        print(
            "--- DEBUG: quit_application() - Verificando estado da janela principal antes de destruir... ---"
        )
        try:
            if hasattr(self, "winfo_exists") and self.winfo_exists():
                print(
                    "--- DEBUG: quit_application() - Janela principal existe. Chamando super().destroy()... ---"
                )
                super().destroy()
                print(
                    "--- DEBUG: quit_application() - super().destroy() FOI CHAMADO. ---"
                )
            else:
                print(
                    "--- DEBUG: quit_application() - Janela principal já não existe ou é inválida antes de super().destroy(). ---"
                )
        except Exception as e_destroy:
            print(
                f"--- DEBUG: quit_application() - ERRO durante super().destroy(): {e_destroy} ---"
            )
            import traceback

            traceback.print_exc()

        print(
            "--- DEBUG: quit_application() - Aplicação deve ser encerrada. Forçando saída com sys.exit(0)... ---"
        )
        sys.exit(0)

    # Modifique sua função on_closing:
    def on_closing(
        self,
    ):  # Renomeada de quit_application para o fluxo original de fechamento lógico
        print("--- DEBUG: Lógica de on_closing() sendo executada ---")
        print("UI: Fechando aplicação (lógica interna)...")
        self.save_app_data()
        self.stop_auto_monitoring()  # Tenta parar a thread de monitoramento

        # Espera pela thread de monitoramento (se estiver rodando)
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            print("UI: Aguardando thread de monitoramento finalizar antes de fechar...")
            # O timeout aqui pode ser ajustado
            self.monitoring_thread.join(
                timeout=max(2, self.AUTO_MONITOR_INTERVAL_SECONDS // 1000 + 1)
            )

        # A destruição da janela e parada do ícone da bandeja são feitas por quit_application
        # que por sua vez chama self.destroy() e sys.exit()
        # Aqui, apenas preparamos para o fechamento.

        # Se quit_application foi chamada pelo menu da bandeja, ela fará o self.destroy()
        # Se hide_to_tray foi chamada, esta função on_closing não deveria ser chamada diretamente pelo "X"
        # O botão "X" agora chama hide_to_tray.
        # Esta on_closing() é mais para a lógica de 'preparar para fechar'
        print("--- DEBUG: Lógica de on_closing() concluída ---")

    # Adicione este método para ser chamado pela opção "Fechar" da bandeja
    def quit_from_tray_menu(self):
        print("Tray: Comandado Fechar Limpador.")
        self.quit_application()  # Chama a função que realmente fecha tudo

    # Modifique sua chamada principal no final do arquivo:
    # if __name__ == "__main__":
    #    app = App()
    #    # app.protocol("WM_DELETE_WINDOW", app.on_closing) # MUDAMOS ISSO PARA hide_to_tray no __init__
    #    # A lógica de on_closing agora é parte de quit_application
    #    app.mainloop()
    # A quit_application fará self.destroy() e sys.exit()
    # A on_closing original agora é chamada por quit_application para salvar e parar threads.

    # Ajuste o método quit_application para ser o ponto final de saída

    def on_closing_logic(
        self,
    ):  # Lógica que estava em on_closing antes, para salvar e parar monitoramento
        print(
            "--- DEBUG: on_closing_logic() INICIADA (salvar e parar monitoramento) ---"
        )
        self.save_app_data()  # Esta função já deve ter seus próprios prints de depuração

        print("--- DEBUG: on_closing_logic() - Chamando stop_auto_monitoring()... ---")
        self.stop_auto_monitoring()  # Esta função já deve ter seus próprios prints de depuração

        if self.monitoring_thread and self.monitoring_thread.is_alive():
            print(
                "--- DEBUG: on_closing_logic() - Aguardando thread de monitoramento finalizar... ---"
            )
            # Usar um timeout fixo para o join durante o teste pode ser mais simples de analisar
            timeout_join_monitor = 5  # segundos
            print(
                f"--- DEBUG: on_closing_logic() - Usando timeout de {timeout_join_monitor}s para join do monitoring_thread ---"
            )
            self.monitoring_thread.join(timeout=timeout_join_monitor)
            if self.monitoring_thread.is_alive():
                print(
                    "--- DEBUG: on_closing_logic() - AVISO: Thread de monitoramento AINDA ESTÁ ATIVA após join. ---"
                )
            else:
                print(
                    "--- DEBUG: on_closing_logic() - Thread de monitoramento finalizada. ---"
                )
        else:
            print(
                "--- DEBUG: on_closing_logic() - Thread de monitoramento não estava ativa ou não existe. ---"
            )
        print("--- DEBUG: on_closing_logic() CONCLUÍDA. ---")

    def analyze_all_projects_action(self):
        self.log_message(
            "Botão 'Analisar Todos os Projetos' clicado.", level="ACTION"
        )  # <--- LOG ADICIONADO

        self.global_status_label.configure(
            text="Status Global: Analisando todos os projetos..."
        )
        self.log_message(
            "Status Global alterado para: Analisando todos os projetos...",
            level="DEBUG",
        )  # <--- LOG ADICIONADO

        if not self.project_widgets:
            self.log_message(
                "Nenhum projeto na lista para analisar.", level="WARNING"
            )  # <--- LOG ADICIONADO
            self.global_status_label.configure(
                text="Status Global: Nenhum projeto na lista para analisar."
            )
            return

        self.log_message(
            f"Iniciando análise para {len(self.project_widgets)} projeto(s).",
            level="INFO",
        )  # <--- LOG ADICIONADO
        for widget_info in self.project_widgets:
            project_data = widget_info["data"]
            project_name = project_data.get(
                "name", "NomeDesconhecido"
            )  # Pega o nome para o log
            cache_label = widget_info["cache_info_label"]

            self.log_message(
                f"Disparando verificação de cache para o projeto: {project_name}",
                level="DEBUG",
            )  # <--- LOG ADICIONADO
            # Reutiliza a lógica de verificação de cache individual
            self.start_verify_cache_thread(
                project_data, cache_label
            )  # Esta função já deve ter seus próprios logs internos se necessário

        self.global_status_label.configure(
            text="Status Global: Análise iniciada para todos os projetos."
        )
        self.log_message(
            "Status Global alterado para: Análise iniciada para todos os projetos.",
            level="DEBUG",
        )  # <--- LOG ADICIONADO

    def clean_allowed_projects_action(self):
        self.log_message("Botão 'Limpar Projetos Permitidos' clicado.", level="ACTION")
        if (
            hasattr(self, "global_status_label")
            and self.global_status_label.winfo_exists()
        ):
            self.global_status_label.configure(
                text="Status Global: Iniciando limpeza de projetos permitidos..."
            )

        cleaned_projects_count = (
            0  # Contará projetos que tiveram pelo menos um item limpo
        )
        total_space_freed_overall = 0
        projects_processed_for_cleaning = (
            0  # Contará projetos que foram elegíveis para limpeza (permitida e fechado)
        )

        if not self.project_widgets:
            self.log_message("Nenhum projeto na lista para limpar.", level="INFO")
            if (
                hasattr(self, "global_status_label")
                and self.global_status_label.winfo_exists()
            ):
                self.global_status_label.configure(
                    text="Status Global: Nenhum projeto na lista para limpar."
                )
            return

        for (
            widget_info_item
        ) in (
            self.project_widgets
        ):  # Renomeado para evitar conflito com a variável do loop interno
            project_data = widget_info_item.get("data", {})
            project_path = project_data.get("path")
            project_name = project_data.get("name", "Desconhecido_Action")

            if not project_path:
                self.log_message(
                    f"Limpeza Global: Projeto '{project_name}' sem caminho. Pulando.",
                    level="WARNING",
                )
                continue

            allow_clean_cb = widget_info_item.get("allow_clean_checkbox")
            cache_label = widget_info_item.get(
                "cache_info_label"
            )  # O cache_info_label do projeto
            folder_checkboxes_map = widget_info_item.get("folder_checkboxes", {})

            if not (
                allow_clean_cb and cache_label and folder_checkboxes_map is not None
            ):
                self.log_message(
                    f"Limpeza Global: Widgets de controle faltando para '{project_name}'. Pulando.",
                    level="WARNING",
                )
                continue

            if allow_clean_cb.get() == 1:  # Se "Permitir Limpeza (Geral)" está marcado
                self.log_message(
                    f"Limpeza Global: Verificando projeto '{project_name}' para limpeza (Permitir Limpeza ON).",
                    level="INFO",
                )
                if (
                    hasattr(cache_label, "winfo_exists") and cache_label.winfo_exists()
                ):  # Verifica se o label ainda existe
                    self.after(
                        0,
                        self._update_cache_info_label,
                        cache_label,
                        "Cache: Verificando para limpeza global...",
                    )

                if is_unreal_project_open(project_path):  # Função de backend global
                    self.log_message(
                        f"Limpeza Global: Projeto '{project_name}' está aberto. Pulando.",
                        level="WARNING",
                    )
                    if (
                        hasattr(cache_label, "winfo_exists")
                        and cache_label.winfo_exists()
                    ):
                        self.after(
                            0,
                            self._update_cache_info_label,
                            cache_label,
                            "Cache: (Global: Pulado - Projeto Aberto)",
                        )
                    continue  # Pula para o próximo projeto

                projects_processed_for_cleaning += (
                    1  # Contabiliza que este projeto foi elegível e processado
                )

                # Obter os itens selecionados para este projeto
                selected_items_for_cleaning = [
                    item_id
                    for item_id, chk_data in folder_checkboxes_map.items()
                    if chk_data.get("var") and chk_data["var"].get() == "on"
                ]

                if not selected_items_for_cleaning:
                    self.log_message(
                        f"Limpeza Global: Nenhum item específico selecionado para limpeza em '{project_name}'. Limpeza não realizada para este projeto.",
                        level="INFO",
                    )
                    if (
                        hasattr(cache_label, "winfo_exists")
                        and cache_label.winfo_exists()
                    ):
                        self.after(
                            0,
                            self._update_cache_info_label,
                            cache_label,
                            "Cache: (Global: Nada selecionado)",
                        )
                    continue  # Pula para o próximo projeto

                self.log_message(
                    f"Limpeza Global: Itens selecionados para '{project_name}': {selected_items_for_cleaning}",
                    level="DEBUG",
                )
                if hasattr(cache_label, "winfo_exists") and cache_label.winfo_exists():
                    self.after(
                        0,
                        self._update_cache_info_label,
                        cache_label,
                        "Cache: (Global: Limpando itens selecionados...)",
                    )

                # Para o botão global, a limpeza de cada projeto é feita sequencialmente aqui.
                # Se a limpeza de um projeto for muito demorada, a UI pode parecer travada.
                # Uma melhoria futura seria enfileirar tarefas de limpeza em threads separadas.

                (
                    space_freed_this_project,
                    successfully_deleted_subfolders,
                    errors_this_project,
                ) = clean_project_cache(
                    project_path, self, selected_items_for_cleaning
                )  # Passa self como app_instance

                # ATUALIZA A UI DOS ITENS DE LIMPEZA PARA ESTE PROJETO
                if successfully_deleted_subfolders:
                    # Esta função já está na thread principal da UI, então pode chamar diretamente
                    self.refresh_project_cleanup_items_ui(
                        widget_info_item, successfully_deleted_subfolders
                    )

                msg_details = []
                action_occurred = False
                if successfully_deleted_subfolders or (
                    space_freed_this_project > 0 and not errors_this_project
                ):
                    # Considera que houve limpeza se subpastas foram deletadas OU espaço foi liberado (arquivos soltos) sem erros.
                    msg_details.append(
                        f"Liberado: {format_size(space_freed_this_project)}."
                    )
                    action_occurred = True
                if errors_this_project:
                    msg_details.append(f"{len(errors_this_project)} erro(s).")
                    action_occurred = (
                        True  # Mesmo com erro, uma tentativa de ação ocorreu
                    )

                if action_occurred:
                    cleaned_projects_count += 1  # Conta como um projeto que teve alguma ação de limpeza (sucesso ou erro)
                    total_space_freed_overall += space_freed_this_project

                final_project_msg = (
                    "Global Limpeza: " + " ".join(msg_details)
                    if msg_details
                    else "Global Limpeza: Nenhum item aplicável encontrado ou já limpo."
                )
                self.log_message(
                    f"Limpeza Global: Resultado para '{project_name}': {final_project_msg}",
                    level="INFO",
                )

                if hasattr(cache_label, "winfo_exists") and cache_label.winfo_exists():
                    self.after(
                        0, self._update_cache_info_label, cache_label, final_project_msg
                    )
                    # Re-verificar e atualizar o tamanho do cache no label após a limpeza,
                    # usando os itens que AINDA ESTÃO SELECIONADOS (se algum sobrou) ou uma lista vazia.
                    # Ou, melhor, recalcular com base no que deveria ter sido o alvo original para ver o impacto.

                    # Pega os itens que AINDA ESTÃO selecionados após refresh_project_cleanup_items_ui
                    # (se refresh_project_cleanup_items_ui também desmarcasse os checkboxes, o que não faz atualmente)
                    # Por simplicidade, vamos recalcular com base nos itens que ERAM o alvo original da limpeza.
                    # Se todos foram deletados, o selected_items_for_cleaning estará vazio para o cálculo e dará 0.

                    # Para ter o tamanho atualizado do que *sobrou* dos itens selecionados (se nem tudo foi deletado):
                    # Primeiro, obtemos os checkboxes que AINDA existem para este projeto
                    current_folder_checkboxes_map = widget_info_item.get(
                        "folder_checkboxes", {}
                    )
                    remaining_selected_items_after_clean = [
                        item_id
                        for item_id, chk_data in current_folder_checkboxes_map.items()
                        if chk_data.get("var") and chk_data["var"].get() == "on"
                    ]

                    if remaining_selected_items_after_clean:
                        new_size_bytes = calculate_project_cache_size(
                            project_path, remaining_selected_items_after_clean, self
                        )
                        self.after(
                            0,
                            self._update_cache_info_label,
                            cache_label,
                            f"Cache (Pós-Limpeza Global): {format_size(new_size_bytes)}",
                        )
                    else:  # Se nada mais está selecionado ou todos os itens selecionados foram removidos da UI
                        self.after(
                            0,
                            self._update_cache_info_label,
                            cache_label,
                            f"Cache (Pós-Limpeza Global): 0 B",
                        )

            else:  # Se "Permitir Limpeza (Geral)" não estava marcado
                self.log_message(
                    f"Limpeza Global: Limpeza não permitida para '{project_name}'.",
                    level="DEBUG",
                )

        # Status final da operação global
        final_status_msg = f"Status Global: Limpeza global concluída."
        if (
            projects_processed_for_cleaning > 0
        ):  # Se algum projeto foi elegível para limpeza
            final_status_msg += f" {cleaned_projects_count} de {projects_processed_for_cleaning} projeto(s) processado(s) tiveram itens limpos."
            if total_space_freed_overall > 0:
                final_status_msg += (
                    f" Total liberado: {format_size(total_space_freed_overall)}."
                )
        else:  # Nenhum projeto foi elegível (todos com "Permitir Limpeza" desmarcado ou abertos)
            final_status_msg = "Status Global: Nenhum projeto elegível para limpeza (verifique 'Permitir Limpeza' e se estão fechados)."

        if (
            hasattr(self, "global_status_label")
            and self.global_status_label.winfo_exists()
        ):
            self.global_status_label.configure(text=final_status_msg)
        self.log_message(final_status_msg, level="INFO")

    def load_app_data(self):
        self.log_message("UI: Carregando dados do aplicativo...", level="INFO")

        # Valores padrão que serão usados se o arquivo de configuração não existir ou estiver incompleto
        default_interval_seconds = 3600  # Padrão de 1 hora
        MIN_INTERVAL_MINUTES_DISPLAY = (
            1  # Mínimo de 1 minuto para exibição e configuração na UI
        )
        MIN_INTERVAL_SECONDS_INTERNAL = (
            MIN_INTERVAL_MINUTES_DISPLAY * 60
        )  # Mínimo em segundos para lógica interna

        loaded_interval_seconds_from_json = (
            default_interval_seconds  # Valor que será usado internamente (em segundos)
        )
        auto_start_monitor_pref = (
            False  # Padrão para "Ativar monitoramento automático ao iniciar"
        )
        # auto_start_windows_pref não é carregado do JSON; é verificado diretamente no registro por _check_startup_status()

        # Limpa o estado visual e de controle ANTES de carregar do JSON,
        # para evitar duplicatas ou estados inconsistentes.
        self._clear_project_list_ui()
        self.displayed_project_paths.clear()

        try:
            if os.path.exists(
                ABSOLUTE_CONFIG_PATH
            ):  # ABSOLUTE_CONFIG_PATH é o caminho completo para o JSON
                with open(ABSOLUTE_CONFIG_PATH, "r") as f:
                    data = json.load(f)
                self.log_message(
                    f"Arquivo de configuração '{ABSOLUTE_CONFIG_PATH}' carregado.",
                    level="DEBUG",
                )

                settings = data.get(
                    "settings", {}
                )  # Pega a seção de configurações; {} se não existir

                # Carrega preferência de "Ativar monitoramento automático ao iniciar"
                auto_start_monitor_pref = settings.get(
                    "auto_start_monitoring_on_launch", False
                )

                # Carrega o intervalo de monitoramento (armazenado em segundos no JSON)
                loaded_interval_str = settings.get(
                    "monitoring_interval_seconds", str(default_interval_seconds)
                )
                try:
                    parsed_seconds = int(loaded_interval_str)
                    if (
                        parsed_seconds >= MIN_INTERVAL_SECONDS_INTERNAL
                    ):  # Usa o mínimo em segundos para validação
                        loaded_interval_seconds_from_json = parsed_seconds
                    elif (
                        parsed_seconds > 0
                    ):  # Se for positivo mas menor que o mínimo permitido
                        self.log_message(
                            f"Intervalo carregado ({parsed_seconds}s) é menor que o mínimo de {MIN_INTERVAL_MINUTES_DISPLAY} min. Ajustando para o mínimo.",
                            level="WARNING",
                        )
                        loaded_interval_seconds_from_json = (
                            MIN_INTERVAL_SECONDS_INTERNAL
                        )
                    else:  # Se for 0 ou negativo
                        self.log_message(
                            f"Intervalo (segundos) inválido carregado do JSON (<=0): '{loaded_interval_str}'. Usando padrão: {default_interval_seconds}s.",
                            level="WARNING",
                        )
                        loaded_interval_seconds_from_json = default_interval_seconds
                except ValueError:
                    self.log_message(
                        f"Valor do intervalo (segundos) não numérico carregado do JSON: '{loaded_interval_str}'. Usando padrão: {default_interval_seconds}s.",
                        level="WARNING",
                    )
                    loaded_interval_seconds_from_json = default_interval_seconds

                # Carrega a lista de projetos salvos
                saved_projects = data.get("projects", [])
                self.log_message(
                    f"Encontrados {len(saved_projects)} projetos no arquivo JSON para carregar.",
                    level="DEBUG",
                )

                for i, project_data_from_json in enumerate(saved_projects):
                    project_name_json = project_data_from_json.get(
                        "name", f"ProjetoJSON_{i}"
                    )
                    project_path_from_json = project_data_from_json.get("path")

                    self.log_message(
                        f"LOAD: Processando projeto salvo {i+1}/{len(saved_projects)}: '{project_name_json}' com path '{project_path_from_json}'",
                        level="DEBUG",
                    )

                    if not project_path_from_json:
                        self.log_message(
                            f"LOAD: Projeto salvo '{project_name_json}' não tem caminho. Pulando.",
                            level="WARNING",
                        )
                        continue

                    normalized_path_from_json = os.path.normpath(project_path_from_json)
                    self.log_message(
                        f"LOAD: Path normalizado do JSON para '{project_name_json}': {normalized_path_from_json}",
                        level="TRACE",
                    )

                    project_data_to_add = project_data_from_json.copy()
                    project_data_to_add["path"] = normalized_path_from_json

                    # Adiciona à UI. A verificação de duplicata visual não é estritamente necessária aqui
                    # porque displayed_project_paths foi limpo. add_project_entry_to_ui irá popular
                    # self.project_widgets.
                    self.add_project_entry_to_ui(
                        project_data_to_add, from_saved_data=True
                    )
                    # Adiciona o caminho normalizado ao conjunto de controle após adicionar à UI
                    self.displayed_project_paths.add(normalized_path_from_json)
                    self.log_message(
                        f"LOAD: Projeto '{project_name_json}' adicionado à UI e displayed_paths.",
                        level="TRACE",
                    )

                self.log_message(
                    f"{len(self.project_widgets)} projetos na UI após carregar do JSON.",
                    level="DEBUG",
                )
            else:
                self.log_message(
                    f"Arquivo de configuração não encontrado em '{ABSOLUTE_CONFIG_PATH}'. Nenhum projeto carregado. Usando padrões para configurações.",
                    level="INFO",
                )
                # auto_start_monitor_pref e loaded_interval_seconds_from_json já têm seus defaults definidos no início da função.

        except Exception as e:
            self.log_message(
                f"Erro CRÍTICO ao carregar dados de '{ABSOLUTE_CONFIG_PATH}': {e}",
                level="ERROR",
            )
            import traceback

            traceback.print_exc()
            # Em caso de erro grave ao carregar, reseta para padrões e limpa a lista de projetos
            self._clear_project_list_ui()
            self.displayed_project_paths.clear()
            auto_start_monitor_pref = False
            loaded_interval_seconds_from_json = default_interval_seconds

        # --- Configura os Widgets da UI com os Valores Carregados ou Padrões ---

        # Checkbox "Ativar monitoramento automático ao iniciar o programa"
        if (
            hasattr(self, "auto_start_monitoring_checkbox")
            and self.auto_start_monitoring_checkbox.winfo_exists()
        ):
            if auto_start_monitor_pref:
                self.auto_start_monitoring_checkbox.select()
            else:
                self.auto_start_monitoring_checkbox.deselect()

        # Variável interna para o intervalo (em segundos)
        self.AUTO_MONITOR_INTERVAL_SECONDS = loaded_interval_seconds_from_json

        # Converte o intervalo (que está em segundos) para minutos para exibir na UI
        interval_to_display_in_minutes = loaded_interval_seconds_from_json // 60
        # Se o valor em segundos era > 0 mas < MIN_INTERVAL_SECONDS_INTERNAL, ele já foi ajustado para MIN_INTERVAL_SECONDS_INTERNAL.
        # Então, interval_to_display_in_minutes refletirá isso.

        # Campo de entrada para o intervalo (exibido em minutos)
        if hasattr(
            self, "monitoring_interval_var"
        ):  # Verifica se a StringVar foi criada
            self.monitoring_interval_var.set(str(interval_to_display_in_minutes))
            self.log_message(
                f"LOAD: monitoring_interval_var (UI, minutos) definido para: '{str(interval_to_display_in_minutes)}'",
                level="DEBUG",
            )
        elif (
            hasattr(self, "monitoring_interval_entry")
            and self.monitoring_interval_entry.winfo_exists()
        ):  # Fallback se StringVar não foi usada
            self.monitoring_interval_entry.delete(0, "end")
            self.monitoring_interval_entry.insert(
                0, str(interval_to_display_in_minutes)
            )
            self.log_message(
                f"LOAD: monitoring_interval_entry (UI, minutos) definido para: '{str(interval_to_display_in_minutes)}' (via fallback).",
                level="DEBUG",
            )

        self.log_message(
            f"Intervalo de monitoramento (interno) definido para: {self.AUTO_MONITOR_INTERVAL_SECONDS} segundos.",
            level="INFO",
        )

        # O checkbox "Iniciar com o Windows" é atualizado por self._check_startup_status() no final do __init__

    def save_app_data(self):
        self.log_message("--- DEBUG: save_app_data() FOI CHAMADO ---", level="DEBUG")

        current_working_dir = ""
        try:
            current_working_dir = os.getcwd()
            self.log_message(
                f"--- DEBUG: Salvando em {ABSOLUTE_CONFIG_PATH} (CWD atual: {current_working_dir}) ---",
                level="DEBUG",
            )
        except Exception as e_getcwd:
            self.log_message(
                f"--- DEBUG: Erro ao obter diretório de trabalho: {e_getcwd} ---",
                level="ERROR",
            )

        self.log_message("UI: Preparando dados para salvar...", level="INFO")
        data_to_save = {"projects": [], "settings": {}}

        # --- SALVAR CONFIGURAÇÕES GLOBAIS ---
        # Iniciar com o Windows
        start_with_windows_val = False
        if (
            hasattr(self, "start_with_windows_checkbox")
            and self.start_with_windows_checkbox.winfo_exists()
        ):
            start_with_windows_val = self.start_with_windows_checkbox.get() == 1
        data_to_save["settings"]["start_with_windows"] = start_with_windows_val

        # Ativar monitoramento automático ao iniciar
        auto_start_launch_val = False
        if (
            hasattr(self, "auto_start_monitoring_checkbox")
            and self.auto_start_monitoring_checkbox.winfo_exists()
        ):
            auto_start_launch_val = self.auto_start_monitoring_checkbox.get() == 1
        data_to_save["settings"][
            "auto_start_monitoring_on_launch"
        ] = auto_start_launch_val

        # Intervalo de Monitoramento
        interval_to_save_str = str(self.AUTO_MONITOR_INTERVAL_SECONDS)
        if (
            hasattr(self, "monitoring_interval_entry")
            and self.monitoring_interval_entry.winfo_exists()
        ):
            entry_val_str = self.monitoring_interval_entry.get()
            if entry_val_str:
                try:
                    parsed_interval = int(entry_val_str)
                    if parsed_interval > 0:
                        interval_to_save_str = str(parsed_interval)
                        self.AUTO_MONITOR_INTERVAL_SECONDS = parsed_interval
                    else:
                        self.log_message(
                            f"Valor do intervalo no campo inválido (<=0): '{entry_val_str}'. Usando valor em memória: {self.AUTO_MONITOR_INTERVAL_SECONDS}s.",
                            level="WARNING",
                        )
                except ValueError:
                    self.log_message(
                        f"Valor do intervalo no campo não numérico: '{entry_val_str}'. Usando valor em memória: {self.AUTO_MONITOR_INTERVAL_SECONDS}s.",
                        level="WARNING",
                    )
            else:
                self.log_message(
                    f"Campo de intervalo de monitoramento está vazio. Usando valor em memória: {self.AUTO_MONITOR_INTERVAL_SECONDS}s.",
                    level="DEBUG",
                )

        data_to_save["settings"]["monitoring_interval_seconds"] = str(
            self.AUTO_MONITOR_INTERVAL_SECONDS
        )
        interval_in_minutes_for_log = self.AUTO_MONITOR_INTERVAL_SECONDS // 60
        self.log_message(
            f"Salvando intervalo de monitoramento: {self.AUTO_MONITOR_INTERVAL_SECONDS}s ({interval_in_minutes_for_log} min).",
            level="DEBUG",
        )
        self.log_message(
            f"Configurações a serem salvas: {data_to_save['settings']}", level="DEBUG"
        )
        # --- FIM SALVAR CONFIGURAÇÕES GLOBAIS ---

        # --- SALVAR DADOS DOS PROJETOS ---
        for widget_info_item in self.project_widgets:
            project_data_original = widget_info_item[
                "data"
            ]  # Contém path, name, uproject_file originais

            verify_auto_checkbox = widget_info_item.get("verify_auto_checkbox")
            allow_clean_checkbox = widget_info_item.get("allow_clean_checkbox")
            gb_limit_entry = widget_info_item.get("gb_limit_entry")
            folder_checkboxes_map = widget_info_item.get(
                "folder_checkboxes", {}
            )  # Pega o mapa de checkboxes de pastas

            # Coleta os itens de limpeza selecionados (pastas principais e subpastas)
            selected_cleanup_items = []
            for item_id, chk_data in folder_checkboxes_map.items():
                # item_id é o nome da pasta principal (ex: "Saved") ou o caminho relativo da subpasta (ex: "Saved/Logs")
                # chk_data é {"widget": chk, "var": chk_var, "path": path_original, "is_main_folder": True/False}
                if chk_data["var"].get() == "on":  # Se o checkbox está marcado
                    selected_cleanup_items.append(
                        item_id
                    )  # Salva o ID/caminho relativo

            project_config = {
                "path": project_data_original.get("path", "CAMINHO_AUSENTE"),
                "name": project_data_original.get("name", "NOME_AUSENTE"),
                "uproject_file": project_data_original.get("uproject_file", ""),
                "monitor_auto": (
                    verify_auto_checkbox.get() == 1 if verify_auto_checkbox else False
                ),
                "allow_clean": (
                    allow_clean_checkbox.get() == 1 if allow_clean_checkbox else False
                ),
                "gb_limit": gb_limit_entry.get() if gb_limit_entry else "",
                "selected_cleanup_items": selected_cleanup_items,  # Nova lista de itens selecionados
            }
            data_to_save["projects"].append(project_config)

        self.log_message(
            f"Salvando {len(data_to_save['projects'])} projetos.", level="DEBUG"
        )
        # --- FIM SALVAR DADOS DOS PROJETOS ---

        try:
            self.log_message(
                f"Tentando salvar dados em: {ABSOLUTE_CONFIG_PATH}", level="DEBUG"
            )
            with open(ABSOLUTE_CONFIG_PATH, "w") as f:
                json.dump(data_to_save, f, indent=4)
            self.log_message(
                f"Dados salvos com sucesso em {ABSOLUTE_CONFIG_PATH}.", level="INFO"
            )
        except Exception as e:
            self.log_message(
                f"--- ERRO FATAL AO SALVAR DADOS em '{ABSOLUTE_CONFIG_PATH}': {e} ---",
                level="CRITICAL",
            )
            import traceback

            traceback.print_exc()

    def initial_project_discovery_and_load(self):
        """Escaneia a pasta padrão e adiciona projetos que ainda não foram carregados."""
        # A UI não deve ser limpa aqui, pois já carregamos os projetos salvos.
        # A função discover_unreal_projects será chamada por start_discover_projects_thread.
        # Esta última precisa de um argumento para não limpar a UI.
        self.global_status_label.configure(
            text="Status Global: Escaneando pasta padrão..."
        )
        self.start_discover_projects_thread(clear_current_list=False)

    def _update_cache_info_label(self, cache_info_label_widget, message):
        """Função auxiliar para atualizar o label de info do cache na thread principal."""
        cache_info_label_widget.configure(text=message)

    # --- Ações para Verificar Tamanho do Cache ---
    def _thread_target_verify_cache(self, project_path, cache_info_label_widget):
        """
        Função que roda na thread para calcular o tamanho total do cache potencial
        E o tamanho do cache dos itens SELECIONADOS.
        """
        self.log_message(
            f"VERIFY_SIZE_THREAD: Iniciando para projeto '{project_path}'.",
            level="DEBUG",
        )

        # Inicializa os tamanhos para o caso de erros ou nenhuma seleção
        size_selected_bytes = 0
        size_total_potential_bytes = 0

        # Formato da mensagem de status
        status_message = "Cache: Erro ao verificar"  # Mensagem padrão em caso de erro

        try:
            # 1. Calcular o tamanho total do cache potencial (ex: Intermediate + DerivedDataCache)
            size_total_potential_bytes = calculate_project_total_potential_cache(
                project_path, self
            )  # Passa self como app_instance

            # 2. Calcular o tamanho dos itens selecionados pelo usuário
            selected_items_for_calc = []
            found_project_widget_info = None

            for widget_info_item in self.project_widgets:
                if widget_info_item.get("data", {}).get("path") == project_path:
                    found_project_widget_info = widget_info_item
                    break

            if found_project_widget_info:
                folder_checkboxes_map = found_project_widget_info.get(
                    "folder_checkboxes", {}
                )
                selected_items_for_calc = [
                    item_id
                    for item_id, chk_data in folder_checkboxes_map.items()
                    if chk_data.get("var") and chk_data["var"].get() == "on"
                ]
                self.log_message(
                    f"VERIFY_SIZE_THREAD: Itens selecionados para cálculo em '{project_path}': {selected_items_for_calc}",
                    level="TRACE",
                )
            else:
                self.log_message(
                    f"VERIFY_SIZE_THREAD: Não foi possível encontrar widget_info para '{project_path}'. Não é possível obter itens selecionados.",
                    level="WARNING",
                )

            if selected_items_for_calc:
                size_selected_bytes = calculate_project_cache_size(
                    project_path, selected_items_for_calc, self
                )  # Passa self
            elif not found_project_widget_info:
                self.log_message(
                    f"VERIFY_SIZE_THREAD: Calculando tamanho selecionado como 0 para '{project_path}' pois o widget não foi encontrado.",
                    level="DEBUG",
                )
            else:  # Widget encontrado, mas nada selecionado
                self.log_message(
                    f"VERIFY_SIZE_THREAD: Nenhum item selecionado para cálculo de cache em '{project_path}'. Tamanho selecionado será 0.",
                    level="DEBUG",
                )

            # Monta a string de status final
            status_message = f"Cache Total: {format_size(size_total_potential_bytes)} | Selecionado: {format_size(size_selected_bytes)}"

        except Exception as e:
            self.log_message(
                f"Erro CRÍTICO na thread de verificação de cache para '{project_path}': {e}",
                level="ERROR",
            )
            import traceback

            traceback.print_exc()
            # status_message já é "Cache: Erro ao verificar"

        # Atualiza o label na UI
        if (
            hasattr(cache_info_label_widget, "winfo_exists")
            and cache_info_label_widget.winfo_exists()
        ):
            self.after(
                0,
                self._update_cache_info_label,
                cache_info_label_widget,
                status_message,
            )
        else:
            self.log_message(
                "VERIFY_SIZE_THREAD: cache_info_label_widget não existe mais ao tentar atualizar.",
                level="WARNING",
            )

    def start_verify_cache_thread(self, project_info, cache_info_label_widget):
        """Inicia uma thread para verificar o tamanho do cache do projeto."""
        project_path = project_info["path"]
        self._update_cache_info_label(cache_info_label_widget, "Cache: Verificando...")

        thread = threading.Thread(
            target=self._thread_target_verify_cache,
            args=(project_path, cache_info_label_widget),
        )
        thread.daemon = True
        thread.start()

    # --- Ações para Limpar Cache ---
    def _thread_target_clean_cache(
        self, project_path, cache_info_label_widget, allow_clean_checkbox_widget
    ):
        """Função que roda na thread para limpar o cache."""
        # PRIMEIRO: Verificar se o projeto está aberto (LÓGICA PENDENTE AQUI)
        # if is_unreal_project_open(project_path): # Função a ser criada com psutil
        #     self.after(0, self._update_cache_info_label, cache_info_label_widget, "ERRO: Projeto está aberto!")
        #     return

        try:
            space_freed, cleaned, errors = clean_project_cache(project_path, self)
            if errors:
                msg = f"Limpeza Parcial. Liberado: {format_size(space_freed)}. Erros: {'; '.join(errors)}"
            elif cleaned:
                msg = f"Limpo! Liberado: {format_size(space_freed)}."
            else:
                msg = "Nada para limpar ou pastas não encontradas."

            self.after(0, self._update_cache_info_label, cache_info_label_widget, msg)
            # Opcional: Re-verificar o tamanho automaticamente após a limpeza
            if cleaned:
                self.after(
                    500,
                    self.start_verify_cache_thread,
                    {"path": project_path},
                    cache_info_label_widget,
                )

        except Exception as e:
            print(f"Erro na thread de limpeza de cache: {e}")
            self.after(
                0,
                self._update_cache_info_label,
                cache_info_label_widget,
                "Cache: Erro ao limpar",
            )

    def start_clean_cache_thread(
        self, project_info, allow_clean_checkbox_widget, cache_info_label_widget
    ):
        """Inicia uma thread para limpar o cache do projeto."""
        project_path = project_info["path"]

        if (
            not allow_clean_checkbox_widget.get()
        ):  # .get() retorna 1 se marcado, 0 se desmarcado
            self._update_cache_info_label(
                cache_info_label_widget, "Limpeza não permitida (marque a caixa)."
            )
            return

        self._update_cache_info_label(cache_info_label_widget, "Cache: Limpando...")

        thread = threading.Thread(
            target=self._thread_target_clean_cache,
            args=(
                project_path,
                cache_info_label_widget,
                allow_clean_checkbox_widget,
            ),  # Passa o checkbox para futuras checagens dentro da thread se necessário
        )
        thread.daemon = True
        thread.start()

    def prompt_add_project_manually(self):
        """Abre uma caixa de diálogo para o usuário selecionar uma pasta de projeto."""
        # CORRIGIDO AQUI:
        self.global_status_label.configure(
            text="Status Global: Selecionando pasta para adição manual..."
        )

        folder_selected = filedialog.askdirectory(
            title="Selecione a Pasta do Projeto Unreal"
        )

        if folder_selected:
            print(f"UI: Pasta selecionada manualmente: {folder_selected}")
            project_info = self.validate_unreal_project_folder(
                folder_selected
            )  # Esta função já retorna o nome do .uproject
            if project_info:
                if project_info["path"] not in self.displayed_project_paths:
                    self.add_project_entry_to_ui(
                        project_info, from_saved_data=False
                    )  # from_saved_data é False para adição manual
                    # self.displayed_project_paths.add(project_info["path"]) # Isso agora é feito dentro de add_project_entry_to_ui
                    # CORRIGIDO AQUI:
                    self.global_status_label.configure(
                        text=f"Status Global: Projeto '{project_info['name']}' adicionado manualmente."
                    )
                else:
                    # CORRIGIDO AQUI:
                    self.global_status_label.configure(
                        text=f"Status Global: Projeto '{project_info['name']}' já está na lista."
                    )
            else:
                # CORRIGIDO AQUI:
                self.global_status_label.configure(
                    text="Status Global: Pasta selecionada não é um projeto Unreal válido."
                )
        else:
            # CORRIGIDO AQUI:
            self.global_status_label.configure(
                text="Status Global: Adição manual cancelada."
            )

    def validate_unreal_project_folder(self, folder_path):
        """
        Verifica se a pasta fornecida contém um arquivo .uproject.
        Retorna um dicionário com informações do projeto se válido, senão None.
        """
        if not os.path.isdir(folder_path):
            return None

        project_file_found = None
        for item_name in os.listdir(folder_path):
            if item_name.endswith(".uproject"):
                project_file_found = item_name
                break

        if project_file_found:
            project_name = os.path.basename(folder_path)
            return {
                "name": project_name,
                "path": folder_path,
                "uproject_file": project_file_found,
            }
        return None

    def start_discover_projects_thread(
        self, clear_current_list=True
    ):  # <--- CORREÇÃO AQUI
        """
        Inicia uma thread para descobrir projetos Unreal na pasta padrão.
        Se clear_current_list for True, limpa a lista de projetos exibida antes de escanear.
        """
        if clear_current_list:
            self.global_status_label.configure(
                text="Status Global: Limpando lista e procurando projetos..."
            )
            self._clear_project_list_ui()  # Limpa visualmente
            self.displayed_project_paths.clear()  # Limpa controle de duplicatas
        else:
            self.global_status_label.configure(
                text="Status Global: Procurando novos projetos na pasta padrão (sem limpar existentes)..."
            )

        thread = threading.Thread(
            target=discover_unreal_projects,
            # A função discover_unreal_projects também aceita clear_ui_on_start,
            # mas não o usa diretamente para limpar a UI, pois isso é feito aqui.
            # No entanto, podemos manter o argumento se planejamos usá-lo no backend no futuro.
            # Por agora, o terceiro argumento (clear_current_list) para discover_unreal_projects
            # não está sendo usado ativamente naquela função para limpar a UI,
            # mas não causa mal.
            args=(UNREAL_PROJECTS_DEFAULT_PATH, self, clear_current_list),
        )
        thread.daemon = True
        thread.start()

    def _clear_project_list_ui(self):
        """Limpa todos os widgets da lista de projetos na UI."""
        for widget_info in self.project_widgets:
            widget_info["frame"].destroy()
        self.project_widgets = []

    def update_project_list_ui_from_discovery(self, projects_data, error_message):
        self.log_message(
            f"--- DEBUG: update_project_list_ui_from_discovery INÍCIO ---",
            level="DEBUG",
        )
        # Não limpa a UI aqui. A limpeza é feita por start_discover_projects_thread se clear_current_list=True.
        # Se clear_current_list=False (como na inicialização), queremos ADICIONAR aos já carregados.

        if error_message:
            self.log_message(
                f"Erro na descoberta automática de projetos: {error_message}",
                level="ERROR",
            )
            if (
                hasattr(self, "global_status_label")
                and self.global_status_label.winfo_exists()
            ):
                self.global_status_label.configure(
                    text=f"Status Global: Erro na descoberta - {error_message}"
                )
            return

        added_now_count = 0
        updated_count = 0  # Para projetos já existentes que podem ter dados atualizados

        if projects_data:
            self.log_message(
                f"DISCOVERY: Recebidos {len(projects_data)} projetos da varredura.",
                level="DEBUG",
            )
            for project_info_from_discovery in projects_data:
                path_from_discovery = project_info_from_discovery.get("path")
                name_from_discovery = project_info_from_discovery.get(
                    "name", "Desconhecido_Discovery"
                )

                if not path_from_discovery:
                    self.log_message(
                        f"DISCOVERY: Projeto '{name_from_discovery}' sem caminho. Pulando.",
                        level="WARNING",
                    )
                    continue

                normalized_path_from_discovery = os.path.normpath(path_from_discovery)
                project_data_to_process = project_info_from_discovery.copy()
                project_data_to_process["path"] = normalized_path_from_discovery

                # add_project_entry_to_ui vai verificar se já existe em displayed_project_paths
                # e não vai adicionar visualmente de novo se from_saved_data=False.
                # Ele também adiciona a displayed_project_paths se for realmente novo.

                # Precisamos saber se era novo ANTES de chamar add_project_entry_to_ui
                is_new_to_display = (
                    normalized_path_from_discovery not in self.displayed_project_paths
                )

                self.add_project_entry_to_ui(
                    project_data_to_process, from_saved_data=False
                )

                if (
                    is_new_to_display
                    and normalized_path_from_discovery in self.displayed_project_paths
                ):
                    added_now_count += 1
                elif (
                    not is_new_to_display
                ):  # Se não era novo, consideramos como 'verificado/atualizado'
                    updated_count += 1
        else:
            self.log_message(
                "DISCOVERY: Nenhum projeto retornado pela varredura.", level="DEBUG"
            )

        # Atualiza o status global
        current_total_projects = len(self.project_widgets)
        status_msg = f"Status Global: {current_total_projects} projeto(s) listado(s)."
        if added_now_count > 0:
            status_msg += f" ({added_now_count} novo(s) da varredura)"
        elif (
            projects_data and updated_count == len(projects_data) and updated_count > 0
        ):  # Se todos da varredura já existiam
            status_msg += " (Nenhum novo da varredura)"
        elif (
            not projects_data and current_total_projects > 0
        ):  # Nenhum dado da varredura, mas temos projetos carregados
            pass  # Mantém o status de "X projetos listados"
        elif not current_total_projects:  # Nenhnum projeto de lugar nenhum
            status_msg = "Status Global: Nenhum projeto encontrado."

        if (
            hasattr(self, "global_status_label")
            and self.global_status_label.winfo_exists()
        ):
            self.global_status_label.configure(text=status_msg)
        self.log_message(
            f"DISCOVERY: Status final da operação: {status_msg}", level="INFO"
        )

        self.log_message(
            f"--- DEBUG: update_project_list_ui_from_discovery FIM ---", level="DEBUG"
        )

    def add_project_entry_to_ui(self, project_info, from_saved_data=False):
        project_name = project_info.get("name", "Nome Desconhecido")
        project_path = project_info.get("path")

        if not project_path:
            self.log_message(
                f"ADD_UI: Projeto '{project_name}' (dados: {project_info}) sem caminho. Pulando.",
                level="WARNING",
            )
            return

        normalized_project_path = os.path.normpath(project_path)
        project_info["path"] = normalized_project_path

        self.log_message(
            f"ADD_UI: Processando para '{project_name}' (Path: {normalized_project_path}), from_saved_data={from_saved_data}",
            level="DEBUG",
        )

        if (
            not from_saved_data
            and normalized_project_path in self.displayed_project_paths
        ):
            self.log_message(
                f"ADD_UI: Projeto {project_name} ({normalized_project_path}) já existe na UI (descoberta). Verificando dados internos.",
                level="DEBUG",
            )
            for widget_info_item in self.project_widgets:
                if widget_info_item["data"]["path"] == normalized_project_path:
                    if (
                        widget_info_item["data"] != project_info
                    ):  # Apenas atualiza se os dados realmente mudaram
                        self.log_message(
                            f"ADD_UI: Atualizando dados internos para o projeto existente '{project_name}'.",
                            level="TRACE",
                        )
                        widget_info_item["data"].update(project_info)
                        if (
                            "name_label" in widget_info_item
                            and widget_info_item["name_label"].cget("text")
                            != project_name
                        ):
                            widget_info_item["name_label"].configure(text=project_name)
                        if (
                            "path_label" in widget_info_item
                            and widget_info_item["path_label"].cget("text")
                            != f"({normalized_project_path})"
                        ):
                            widget_info_item["path_label"].configure(
                                text=f"({normalized_project_path})"
                            )
                    break
            return

        self.log_message(
            f"ADD_UI: Criando nova entrada na UI para '{project_name}'.", level="INFO"
        )

        project_frame = ctk.CTkFrame(self.project_scrollable_frame)
        project_frame.pack(fill="x", pady=5, padx=5)

        top_info_frame = ctk.CTkFrame(project_frame)
        top_info_frame.pack(fill="x", padx=5, pady=(5, 2))
        name_label_ui = ctk.CTkLabel(
            top_info_frame, text=f"{project_name}", font=ctk.CTkFont(weight="bold")
        )
        name_label_ui.pack(side="left", padx=(0, 5))
        path_label_ui = ctk.CTkLabel(
            top_info_frame,
            text=f"({normalized_project_path})",
            font=ctk.CTkFont(size=9),
            anchor="w",
        )
        path_label_ui.pack(side="left", padx=0, expand=True, fill="x")
        cache_info_label_ui = ctk.CTkLabel(
            top_info_frame, text="Cache: -", width=150, anchor="e"
        )
        cache_info_label_ui.pack(side="right", padx=5)

        main_controls_frame = ctk.CTkFrame(project_frame)
        main_controls_frame.pack(fill="x", padx=5, pady=(2, 5))
        verify_auto_checkbox_ui = ctk.CTkCheckBox(
            main_controls_frame, text="Monitorar Auto"
        )
        verify_auto_checkbox_ui.pack(side="left", padx=5)
        allow_clean_checkbox_ui = ctk.CTkCheckBox(
            main_controls_frame, text="Permitir Limpeza (Geral)"
        )
        allow_clean_checkbox_ui.pack(side="left", padx=5)
        gb_limit_label_ui = ctk.CTkLabel(main_controls_frame, text="Limite GB (Auto):")
        gb_limit_label_ui.pack(side="left", padx=(10, 0))
        gb_limit_entry_ui = ctk.CTkEntry(
            main_controls_frame, width=50, placeholder_text="Ex: 5"
        )
        gb_limit_entry_ui.pack(side="left", padx=5)
        remove_button_ui = ctk.CTkButton(
            main_controls_frame,
            text="Remover Projeto",
            command=lambda p_info=project_info.copy(): self.remove_project_entry(
                p_info
            ),
            width=100,
        )
        remove_button_ui.pack(side="right", padx=5)

        cleanup_items_main_frame = ctk.CTkFrame(project_frame, fg_color="transparent")
        cleanup_items_main_frame.pack(fill="x", padx=5, pady=(5, 5))

        folder_checkboxes_map = {}
        main_folders_to_scan = ["Intermediate", "DerivedDataCache", "Saved"]

        for main_folder_name in main_folders_to_scan:
            main_folder_abs_path = os.path.join(
                normalized_project_path, main_folder_name
            )
            self.log_message(
                f"ADD_UI: Verificando pasta principal '{main_folder_name}' em '{main_folder_abs_path}' (para '{project_name}')",
                level="TRACE",
            )

            main_folder_header_frame = ctk.CTkFrame(
                cleanup_items_main_frame, fg_color="transparent"
            )
            main_folder_header_frame.pack(fill="x", pady=(3, 0))

            main_folder_id = (
                main_folder_name  # ID para o checkbox da pasta principal (ex: "Saved")
            )
            main_chk_var = ctk.StringVar(value="off")
            main_chk = ctk.CTkCheckBox(
                main_folder_header_frame,
                text=f" {main_folder_name} (arquivos soltos na raiz desta pasta)",
                variable=main_chk_var,
                onvalue="on",
                offvalue="off",
            )
            main_chk.pack(side="left", padx=5)
            folder_checkboxes_map[main_folder_id] = {
                "widget": main_chk,
                "var": main_chk_var,
                "path": main_folder_name,
                "is_main_folder": True,
            }

            subfolders_frame_ui = ctk.CTkFrame(
                cleanup_items_main_frame, fg_color="transparent"
            )
            # pack deste frame é feito por toggle_visibility

            toggle_button_text_prefix = f"Subpastas de {main_folder_name}"
            toggle_button = ctk.CTkButton(
                main_folder_header_frame,
                text=f"{toggle_button_text_prefix} ▼",
                font=ctk.CTkFont(size=10),
                height=20,
                width=180,
                anchor="w",
            )
            toggle_button.configure(
                command=lambda sf=subfolders_frame_ui, btn=toggle_button, t_prefix=toggle_button_text_prefix: self.toggle_visibility(
                    sf, btn, t_prefix
                )
            )
            toggle_button.pack(side="left", padx=10)

            if os.path.exists(main_folder_abs_path) and os.path.isdir(
                main_folder_abs_path
            ):
                subfolders_found_count = 0
                try:
                    for sub_item_name in sorted(os.listdir(main_folder_abs_path)):
                        sub_item_abs_path = os.path.join(
                            main_folder_abs_path, sub_item_name
                        )
                        if os.path.isdir(sub_item_abs_path):
                            subfolders_found_count += 1
                            relative_subfolder_path = os.path.join(
                                main_folder_name, sub_item_name
                            )
                            normalized_relative_subfolder_path = os.path.normpath(
                                relative_subfolder_path
                            )
                            subfolder_desc = KNOWN_SUBFOLDER_DESCRIPTIONS.get(
                                normalized_relative_subfolder_path, "Subpasta."
                            )

                            item_frame = ctk.CTkFrame(subfolders_frame_ui)
                            item_frame.pack(fill="x")
                            chk_var_sub = ctk.StringVar(value="off")
                            chk_sub = ctk.CTkCheckBox(
                                item_frame,
                                text=f" {normalized_relative_subfolder_path}",
                                variable=chk_var_sub,
                                onvalue="on",
                                offvalue="off",
                            )
                            chk_sub.pack(side="left", padx=25, pady=1)
                            folder_checkboxes_map[
                                normalized_relative_subfolder_path
                            ] = {
                                "widget": chk_sub,
                                "var": chk_var_sub,
                                "path": normalized_relative_subfolder_path,
                                "is_main_folder": False,
                            }
                            desc_label_sub = ctk.CTkLabel(
                                item_frame,
                                text=f"({subfolder_desc})",
                                font=ctk.CTkFont(size=9),
                                anchor="w",
                            )
                            desc_label_sub.pack(
                                side="left", padx=5, pady=1, expand=True, fill="x"
                            )
                    if subfolders_found_count == 0:
                        ctk.CTkLabel(
                            subfolders_frame_ui,
                            text=" (Nenhuma subpasta encontrada)",
                            font=ctk.CTkFont(size=9, slant="italic"),
                        ).pack(fill="x", anchor="w", padx=25, pady=1)
                        toggle_button.configure(
                            state="disabled",
                            text=f"{toggle_button_text_prefix} (vazio)",
                        )
                except Exception as e_list_sub:
                    self.log_message(
                        f"ADD_UI: Erro ao listar subitens de {main_folder_abs_path}: {e_list_sub}",
                        level="ERROR",
                    )
                    ctk.CTkLabel(
                        subfolders_frame_ui,
                        text=" (Erro ao listar subpastas)",
                        font=ctk.CTkFont(size=9, slant="italic"),
                    ).pack(fill="x", anchor="w", padx=25, pady=1)
                    toggle_button.configure(
                        state="disabled", text=f"{toggle_button_text_prefix} (erro)"
                    )
            else:
                toggle_button.configure(
                    state="disabled",
                    text=f"{toggle_button_text_prefix} (pasta não encontrada)",
                )
                ctk.CTkLabel(
                    main_folder_header_frame,
                    text="(Pasta principal não encontrada)",
                    font=ctk.CTkFont(size=9, slant="italic"),
                ).pack(side="left", padx=5)

        widget_references = {
            "frame": project_frame,
            "data": project_info.copy(),
            "name_label": name_label_ui,
            "path_label": path_label_ui,
            "cache_info_label": cache_info_label_ui,
            "verify_auto_checkbox": verify_auto_checkbox_ui,
            "allow_clean_checkbox": allow_clean_checkbox_ui,
            "gb_limit_entry": gb_limit_entry_ui,
            "folder_checkboxes": folder_checkboxes_map,
            "remove_button": remove_button_ui,
            # Não armazenamos mais o toggle_button único, pois são múltiplos
        }
        self.project_widgets.append(widget_references)

        if from_saved_data:
            self.log_message(
                f"ADD_UI: Configurando valores para '{project_name}' a partir de dados salvos.",
                level="TRACE",
            )
            if project_info.get("monitor_auto", False):
                verify_auto_checkbox_ui.select()
            else:
                verify_auto_checkbox_ui.deselect()
            if project_info.get("allow_clean", False):
                allow_clean_checkbox_ui.select()
            else:
                allow_clean_checkbox_ui.deselect()

            gb_limit_val = project_info.get("gb_limit", "")
            gb_limit_entry_ui.delete(0, "end")
            if gb_limit_val is not None:
                gb_limit_entry_ui.insert(0, str(gb_limit_val))

            # --- CARREGAR ESTADO DOS CHECKBOXES DE LIMPEZA (PRINCIPAIS E SUBPASTAS) ---
            selected_items = project_info.get("selected_cleanup_items", [])
            self.log_message(
                f"ADD_UI: Itens de limpeza salvos para '{project_name}': {selected_items}",
                level="TRACE",
            )
            for item_id, chk_info_dict in folder_checkboxes_map.items():
                # item_id é o nome da pasta principal (ex: "Saved") ou o caminho relativo da subpasta (ex: os.path.normpath("Saved/Logs"))
                if item_id in selected_items:
                    chk_info_dict["var"].set("on")
                else:
                    chk_info_dict["var"].set("off")
            # --------------------------------------------------------------------------
        else:
            self.displayed_project_paths.add(normalized_project_path)
            self.log_message(
                f"ADD_UI: Projeto NOVO '{project_name}' ({normalized_project_path}) adicionado a displayed_project_paths.",
                level="DEBUG",
            )
            # Configurações padrão para novos projetos:
            allow_clean_checkbox_ui.select()  # Ex: Marcar "Permitir Limpeza (Geral)" por padrão
            # Marcar algumas pastas/subpastas por padrão para limpeza se desejar:
            # if folder_checkboxes_map.get("Intermediate"): # Checkbox da pasta principal Intermediate
            #     folder_checkboxes_map["Intermediate"]["var"].set("on")
            # if folder_checkboxes_map.get(os.path.normpath("Saved/Logs")): # Checkbox da subpasta Saved/Logs
            #     folder_checkboxes_map[os.path.normpath("Saved/Logs")]["var"].set("on")

    def _auto_monitoring_loop(self):
        self.log_message(
            f"Thread de monitoramento automático iniciada. Intervalo configurado: {self.AUTO_MONITOR_INTERVAL_SECONDS}s",
            level="INFO",
        )
        if (
            hasattr(self, "monitoring_status_label")
            and self.monitoring_status_label.winfo_exists()
        ):
            self.after(
                0,
                self.monitoring_status_label.configure,
                {"text": "Monitoramento Automático: Ativo"},
            )

        while not self.monitoring_stop_event.is_set():
            self.log_message(
                "Monitoramento: Iniciando novo ciclo de verificação...", level="DEBUG"
            )
            if (
                hasattr(self, "monitoring_status_label")
                and self.monitoring_status_label.winfo_exists()
            ):
                self.after(
                    0,
                    self.monitoring_status_label.configure,
                    {"text": "Monitoramento Automático: Verificando..."},
                )

            for project_widget_info in self.project_widgets:
                if self.monitoring_stop_event.is_set():
                    self.log_message(
                        "Monitoramento: Evento de parada detectado durante a varredura de projetos.",
                        level="DEBUG",
                    )
                    break

                project_data = project_widget_info.get("data", {})
                project_path = project_data.get("path")
                project_name = project_data.get("name", "Desconhecido_Loop")

                if not project_path:
                    self.log_message(
                        f"Monitoramento: Projeto '{project_name}' sem caminho. Pulando.",
                        level="WARNING",
                    )
                    continue

                monitor_auto_checkbox = project_widget_info.get("verify_auto_checkbox")
                allow_clean_checkbox = project_widget_info.get("allow_clean_checkbox")
                gb_limit_entry = project_widget_info.get("gb_limit_entry")
                cache_info_label = project_widget_info.get("cache_info_label")
                folder_checkboxes_map = project_widget_info.get("folder_checkboxes", {})

                if not (
                    monitor_auto_checkbox
                    and allow_clean_checkbox
                    and gb_limit_entry
                    and cache_info_label
                    and folder_checkboxes_map is not None
                ):
                    self.log_message(
                        f"Monitoramento: Widgets de controle faltando para o projeto '{project_name}'. Pulando.",
                        level="WARNING",
                    )
                    continue

                if monitor_auto_checkbox.get() == 1 and allow_clean_checkbox.get() == 1:
                    self.log_message(
                        f"Monitoramento: Verificando '{project_name}' (Monitorar Auto e Permitir Limpeza Geral ON)",
                        level="DEBUG",
                    )

                    if is_unreal_project_open(project_path):
                        self.log_message(
                            f"Monitoramento: Projeto '{project_name}' está aberto, pulando limpeza automática.",
                            level="INFO",
                        )
                        if cache_info_label and cache_info_label.winfo_exists():
                            self.after(
                                0,
                                self._update_cache_info_label,
                                cache_info_label,
                                "Cache: (Auto: Pulado - Aberto)",
                            )
                        continue

                    gb_limit_str = gb_limit_entry.get()
                    if not gb_limit_str:
                        self.log_message(
                            f"Monitoramento: Limite GB não definido para '{project_name}'. Pulando limpeza automática.",
                            level="DEBUG",
                        )
                        if cache_info_label and cache_info_label.winfo_exists():
                            self.after(
                                0,
                                self._update_cache_info_label,
                                cache_info_label,
                                "Cache: (Auto: Sem Limite GB)",
                            )
                        continue

                    try:
                        gb_limit_float = float(gb_limit_str)
                        limit_bytes = gb_limit_float * (1024**3)
                        if limit_bytes < 0:
                            raise ValueError("Limite de GB não pode ser negativo")
                    except ValueError:
                        self.log_message(
                            f"Monitoramento: Limite GB inválido ('{gb_limit_str}') para '{project_name}'. Pulando limpeza automática.",
                            level="WARNING",
                        )
                        if cache_info_label and cache_info_label.winfo_exists():
                            self.after(
                                0,
                                self._update_cache_info_label,
                                cache_info_label,
                                "Cache: (Auto: Limite GB Inválido)",
                            )
                        continue

                    selected_items_for_project = [
                        item_id
                        for item_id, chk_data in folder_checkboxes_map.items()
                        if chk_data["var"].get() == "on"
                    ]

                    if not selected_items_for_project:
                        self.log_message(
                            f"Monitoramento: Projeto '{project_name}' não tem itens selecionados para limpeza/cálculo de cache. Pulando.",
                            level="DEBUG",
                        )
                        if cache_info_label and cache_info_label.winfo_exists():
                            self.after(
                                0,
                                self._update_cache_info_label,
                                cache_info_label,
                                "Cache: (Auto: Nada selecionado)",
                            )
                        continue

                    self.log_message(
                        f"Monitoramento: Itens selecionados para '{project_name}' para cálculo/limpeza: {selected_items_for_project}",
                        level="TRACE",
                    )
                    # A função calculate_project_cache_size precisa ser chamada com app_instance (self)
                    current_cache_size_bytes = calculate_project_cache_size(
                        project_path, selected_items_for_project, self
                    )

                    self.log_message(
                        f"Monitoramento: '{project_name}' - Cache Selecionado Atual: {format_size(current_cache_size_bytes)}, Limite: {format_size(limit_bytes)}",
                        level="INFO",
                    )
                    if cache_info_label and cache_info_label.winfo_exists():
                        self.after(
                            0,
                            self._update_cache_info_label,
                            cache_info_label,
                            f"Cache: {format_size(current_cache_size_bytes)}",
                        )

                    if current_cache_size_bytes > limit_bytes:
                        self.log_message(
                            f"Monitoramento: Cache de '{project_name}' ({format_size(current_cache_size_bytes)}) excedeu o limite de {format_size(limit_bytes)}. Iniciando limpeza automática...",
                            level="INFO",
                        )
                        if cache_info_label and cache_info_label.winfo_exists():
                            self.after(
                                0,
                                self._update_cache_info_label,
                                cache_info_label,
                                "Cache: (Auto Limpeza...)",
                            )

                        # Passa self como app_instance e os itens selecionados
                        space_freed, deleted_subfolder_paths, errors = (
                            clean_project_cache(
                                project_path, self, selected_items_for_project
                            )
                        )

                        # Atualiza a UI dos itens de limpeza se subpastas foram deletadas
                        if deleted_subfolder_paths:
                            self.after(
                                0,
                                self.refresh_project_cleanup_items_ui,
                                project_widget_info,
                                deleted_subfolder_paths,
                            )

                        msg_details = []
                        if deleted_subfolder_paths or (
                            space_freed > 0 and not errors
                        ):  # Se subpastas foram deletadas ou espaço foi liberado sem erros (arquivos soltos)
                            msg_details.append(f"Liberado: {format_size(space_freed)}.")
                        if errors:
                            msg_details.append(f"{len(errors)} erro(s) na limpeza.")

                        final_msg = (
                            "Auto Limpeza: " + " ".join(msg_details)
                            if msg_details
                            else "Auto Limpeza: Nada efetivamente limpo ou erro."
                        )
                        if (
                            not msg_details and not errors
                        ):  # Caso especial: nada a limpar ou nada foi selecionado que existisse
                            if not selected_items_for_project:
                                final_msg = "Auto: Nada selecionado para limpar."
                            else:
                                final_msg = "Auto: Itens selecionados não encontrados ou já limpos."

                        self.log_message(
                            f"Monitoramento: Resultado da limpeza para '{project_name}': {final_msg}",
                            level="INFO",
                        )

                        if cache_info_label and cache_info_label.winfo_exists():
                            self.after(
                                0,
                                self._update_cache_info_label,
                                cache_info_label,
                                final_msg,
                            )
                            # Re-verificar e atualizar o tamanho do cache no label após a limpeza
                            # Usa a mesma lista selected_items_for_project, pois é o que nos interessa para o limite
                            new_size_bytes = calculate_project_cache_size(
                                project_path, selected_items_for_project, self
                            )
                            self.after(
                                0,
                                self._update_cache_info_label,
                                cache_info_label,
                                f"Cache (Pós-Limpeza Auto): {format_size(new_size_bytes)}",
                            )
                    else:
                        self.log_message(
                            f"Monitoramento: Cache de '{project_name}' ({format_size(current_cache_size_bytes)}) está dentro do limite.",
                            level="DEBUG",
                        )
                else:
                    if monitor_auto_checkbox.get() == 1:
                        self.log_message(
                            f"Monitoramento: '{project_name}' - Monitorar Auto ON, mas Permitir Limpeza Geral OFF. Apenas verificando tamanho (se itens selecionados).",
                            level="DEBUG",
                        )
                        # A lógica de apenas verificar tamanho, mesmo que não vá limpar, pode ser útil
                        folder_checkboxes_map_local = project_widget_info.get(
                            "folder_checkboxes", {}
                        )  # Garante que é o do projeto certo
                        selected_items_for_calc_only = [
                            item_id
                            for item_id, chk_data in folder_checkboxes_map_local.items()
                            if chk_data["var"].get() == "on"
                        ]
                        if selected_items_for_calc_only:
                            current_cache_size_bytes_calc_only = (
                                calculate_project_cache_size(
                                    project_path, selected_items_for_calc_only, self
                                )
                            )
                            if cache_info_label and cache_info_label.winfo_exists():
                                self.after(
                                    0,
                                    self._update_cache_info_label,
                                    cache_info_label,
                                    f"Cache: {format_size(current_cache_size_bytes_calc_only)} (Monitorado/Não Limpar)",
                                )
                        elif cache_info_label and cache_info_label.winfo_exists():
                            self.after(
                                0,
                                self._update_cache_info_label,
                                cache_info_label,
                                "Cache: (Nada selecionado para monitorar)",
                            )

            if self.monitoring_stop_event.is_set():
                break

            intervalo_atual = self.AUTO_MONITOR_INTERVAL_SECONDS
            self.log_message(
                f"Monitoramento: Ciclo concluído. Aguardando {intervalo_atual}s para o próximo.",
                level="DEBUG",
            )
            if (
                hasattr(self, "monitoring_status_label")
                and self.monitoring_status_label.winfo_exists()
            ):
                self.after(
                    0,
                    self.monitoring_status_label.configure,
                    {"text": f"Monitoramento Automático: Aguardando..."},
                )

            stopped_early = self.monitoring_stop_event.wait(
                timeout=float(intervalo_atual)
            )
            if stopped_early:
                self.log_message(
                    "Monitoramento: Evento de parada detectado durante a espera. Saindo do loop.",
                    level="DEBUG",
                )
                break

        self.log_message("Thread de monitoramento automático finalizada.", level="INFO")

        def update_label_to_stopped_final_from_thread():
            self.log_message(
                "Atualizando status da UI para 'Monitoramento Parado' (da thread do monitor).",
                level="DEBUG",
            )
            if (
                hasattr(self, "monitoring_status_label")
                and self.monitoring_status_label.winfo_exists()
            ):
                self.monitoring_status_label.configure(
                    text="Monitoramento Automático: Parado"
                )
            else:
                self.log_message(
                    "Não foi possível atualizar o label de status do monitor para 'Parado' (widget não existe?).",
                    level="WARNING",
                )
            if hasattr(self, "tray_icon") and self.tray_icon and self.tray_icon.visible:
                try:
                    self.tray_icon.update_menu()
                except Exception as e_update_menu:
                    self.log_message(
                        f"Erro ao tentar atualizar menu da bandeja após parada: {e_update_menu}",
                        level="WARNING",
                    )

        if hasattr(self, "after"):
            self.after(0, update_label_to_stopped_final_from_thread)

        # Função interna para garantir que a atualização do label ocorra na thread principal
        def update_label_to_stopped_final_from_thread():
            self.log_message(
                "Atualizando status da UI para 'Monitoramento Parado' (da thread do monitor).",
                level="DEBUG",
            )
            if (
                hasattr(self, "monitoring_status_label")
                and self.monitoring_status_label.winfo_exists()
            ):
                self.monitoring_status_label.configure(
                    text="Monitoramento Automático: Parado"
                )

            # --- ATUALIZA OS BOTÕES DA UI PRINCIPAL ---
            if (
                hasattr(self, "start_monitoring_button_ui")
                and self.start_monitoring_button_ui.winfo_exists()
            ):
                self.start_monitoring_button_ui.configure(state="normal")
            if (
                hasattr(self, "stop_monitoring_button_ui")
                and self.stop_monitoring_button_ui.winfo_exists()
            ):
                self.stop_monitoring_button_ui.configure(state="disabled")
            # -----------------------------------------

            if hasattr(self, "tray_icon") and self.tray_icon and self.tray_icon.visible:
                try:
                    self.tray_icon.update_menu()
                except Exception as e_update_menu:
                    self.log_message(
                        f"Erro ao tentar atualizar menu da bandeja após parada: {e_update_menu}",
                        level="WARNING",
                    )

        if hasattr(self, "after"):  # Garante que o método 'after' exista
            self.after(0, update_label_to_stopped_final_from_thread)

    def start_auto_monitoring(self):
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.log_message("Monitoramento automático já está ativo.", level="INFO")
            return

        self.log_message("Iniciando monitoramento automático...", level="INFO")
        self.monitoring_stop_event.clear()
        self.monitoring_thread = threading.Thread(target=self._auto_monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()

        # Atualiza status e botões na UI principal
        if (
            hasattr(self, "monitoring_status_label")
            and self.monitoring_status_label.winfo_exists()
        ):
            self.monitoring_status_label.configure(
                text="Monitoramento Automático: Ativo"
            )
        if (
            hasattr(self, "start_monitoring_button_ui")
            and self.start_monitoring_button_ui.winfo_exists()
        ):
            self.start_monitoring_button_ui.configure(state="disabled")
        if (
            hasattr(self, "stop_monitoring_button_ui")
            and self.stop_monitoring_button_ui.winfo_exists()
        ):
            self.stop_monitoring_button_ui.configure(state="normal")

        self.log_message(
            "Controles da UI de monitoramento atualizados para 'Ativo'.", level="DEBUG"
        )

        # Atualiza menu da bandeja (se existir)
        if (
            hasattr(self, "tray_icon")
            and self.tray_icon
            and hasattr(self.tray_icon, "update_menu")
            and self.tray_icon.visible
        ):
            try:
                self.tray_icon.update_menu()
            except Exception as e_update_menu:
                self.log_message(
                    f"Erro ao tentar atualizar menu da bandeja em start_auto_monitoring: {e_update_menu}",
                    level="WARNING",
                )

    def stop_auto_monitoring(self):
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.log_message(
                "UI: Solicitando parada do monitoramento automático...", level="INFO"
            )
            if (
                hasattr(self, "monitoring_status_label")
                and self.monitoring_status_label.winfo_exists()
            ):
                self.monitoring_status_label.configure(
                    text="Monitoramento Automático: Parando..."
                )
            # Não mexemos nos botões start/stop aqui, pois a thread _auto_monitoring_loop o fará ao terminar.
            self.monitoring_stop_event.set()
        else:
            self.log_message(
                "UI: Monitoramento não estava ativo ou já foi explicitamente parado.",
                level="DEBUG",
            )
            if (
                hasattr(self, "monitoring_status_label")
                and self.monitoring_status_label.winfo_exists()
            ):
                self.monitoring_status_label.configure(
                    text="Monitoramento Automático: Parado"
                )
            if (
                hasattr(self, "start_monitoring_button_ui")
                and self.start_monitoring_button_ui.winfo_exists()
            ):
                self.start_monitoring_button_ui.configure(state="normal")
            if (
                hasattr(self, "stop_monitoring_button_ui")
                and self.stop_monitoring_button_ui.winfo_exists()
            ):
                self.stop_monitoring_button_ui.configure(state="disabled")

            # Atualiza menu da bandeja (se existir)
            if (
                hasattr(self, "tray_icon")
                and self.tray_icon
                and hasattr(self.tray_icon, "update_menu")
                and self.tray_icon.visible
            ):
                try:
                    self.tray_icon.update_menu()
                except Exception as e_update_menu:
                    self.log_message(
                        f"Erro ao tentar atualizar menu da bandeja em stop_auto_monitoring (else): {e_update_menu}",
                        level="WARNING",
                    )

    def on_closing(self):
        print("UI: Fechando aplicação...")
        self.save_app_data()  # Salva os dados antes de fechar
        self.stop_auto_monitoring()
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            print("UI: Aguardando thread de monitoramento finalizar antes de fechar...")
            self.monitoring_thread.join(timeout=5)
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
