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

CONFIG_FILE_NAME = "clean_unreal_config.json"
ABSOLUTE_CONFIG_PATH = os.path.join(APPLICATION_PATH, CONFIG_FILE_NAME)

# --- Configurações Iniciais ---
user_home_path = os.path.expanduser("~")
UNREAL_PROJECTS_DEFAULT_PATH = os.path.join(
    user_home_path, "Documents", "Unreal Projects"
)

# --- Funções de Backend (Lógica do Programa) ---


def discover_unreal_projects(
    base_path, app_instance, clear_ui_on_start=False
):  # Argumento clear_ui_on_start não é usado diretamente aqui, mas mantido para consistência se precisar
    """
    Procura por pastas de projeto Unreal no caminho base fornecido.
    Uma pasta é considerada um projeto se contiver um arquivo .uproject.
    """
    print(f"Backend: Procurando projetos em {base_path}...")
    found_projects = []
    if not os.path.exists(base_path):
        print(f"Backend: Caminho não encontrado: {base_path}")
        # Envia uma mensagem de erro para a UI
        # CORRIGIDO AQUI:
        app_instance.after(
            0,
            app_instance.update_project_list_ui_from_discovery,
            [],
            "Caminho de projetos não encontrado.",
        )
        return

    try:
        for item_name in os.listdir(base_path):
            item_path = os.path.join(base_path, item_name)
            if os.path.isdir(item_path):
                # Verifica se existe um arquivo .uproject dentro desta pasta
                for sub_item in os.listdir(item_path):
                    if sub_item.endswith(".uproject"):
                        project_name = item_name  # O nome da pasta é o nome do projeto
                        # CORRIGIDO AQUI: Adicionar "uproject_file": sub_item
                        found_projects.append(
                            {
                                "name": project_name,
                                "path": item_path,
                                "uproject_file": sub_item,  # Nome do arquivo .uproject
                            }
                        )
                        print(
                            f"Backend: Projeto encontrado: {project_name} em {item_path} ({sub_item})"
                        )
                        break  # Encontrou o .uproject, pode ir para o próximo item_name

        # Depois de encontrar os projetos, pede para a thread principal da UI atualizar a lista
        if not found_projects:
            app_instance.after(
                0,
                app_instance.update_project_list_ui_from_discovery,
                [],
                "Nenhum projeto Unreal encontrado.",
            )
        else:
            app_instance.after(
                0,
                app_instance.update_project_list_ui_from_discovery,
                found_projects,
                None,
            )

    except Exception as e:
        print(f"Backend: Erro ao procurar projetos: {e}")
        app_instance.after(
            0,
            app_instance.update_project_list_ui_from_discovery,
            [],
            f"Erro ao ler projetos: {e}",
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


def calculate_project_cache_size(project_path):
    """Calcula o tamanho total das pastas de cache definidas para um projeto."""
    total_cache_size = 0
    print(f"Backend: Calculando cache para {project_path}...")
    for subfolder in CACHE_SUBFOLDERS_TO_SCAN:
        full_subfolder_path = os.path.join(project_path, subfolder)
        if os.path.exists(full_subfolder_path):
            size = get_folder_size(full_subfolder_path)
            print(f"Backend: Tamanho de {full_subfolder_path} = {format_size(size)}")
            total_cache_size += size
        else:
            print(f"Backend: Pasta de cache não encontrada: {full_subfolder_path}")
    return total_cache_size


def clean_project_cache(project_path, app_instance):
    """Deleta as pastas de cache definidas para um projeto."""
    # IMPORTANTE: Adicionar verificação se o projeto está aberto ANTES de deletar!
    # Esta é uma implementação básica, SEM essa verificação ainda.

    space_freed_total = 0
    cleaned_folders = []
    errors = []

    print(f"Backend: Iniciando limpeza para {project_path}...")
    app_instance.log_message(
        f"Backend: Iniciando limpeza para {project_path}...",
        level="WARNING",
    )
    for subfolder_to_clean in CACHE_SUBFOLDERS_TO_CLEAN:
        full_path_to_clean = os.path.join(project_path, subfolder_to_clean)
        if os.path.exists(full_path_to_clean) and os.path.isdir(full_path_to_clean):
            print(f"Backend: Tentando deletar {full_path_to_clean}...")
            app_instance.log_message(
                f"Backend: Tentando deletar {full_path_to_clean}...",
                level="WARNING",
            )
            try:
                # Calcula o tamanho antes de deletar para reportar o espaço liberado
                folder_size = get_folder_size(full_path_to_clean)
                shutil.rmtree(full_path_to_clean)
                print(f"Backend: Deletado com sucesso: {full_path_to_clean}")
                app_instance.log_message(
                    f"Backend: Deletado com sucesso: {full_path_to_clean}",
                    level="WARNING",
                )
                space_freed_total += folder_size
                cleaned_folders.append(subfolder_to_clean)
            except OSError as e:
                error_msg = f"Erro ao deletar {full_path_to_clean}: {e}"
                app_instance.log_message(
                    f"Backend: {error_msg}",
                    level="ERROR",
                )
                print(f"Backend: {error_msg}")
                errors.append(error_msg)
        else:
            print(
                f"Backend: Pasta não encontrada para limpeza ou não é um diretório: {full_path_to_clean}"
            )
            app_instance.log_message(
                f"Backend: Pasta não encontrada para limpeza ou não é um diretório: {full_path_to_clean}",
                level="WARNING",
            )

    return space_freed_total, cleaned_folders, errors


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
        self.geometry("950x750")

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

        # --- Frame de Configurações de Monitoramento (dentro da aba "Gerenciador") ---
        self.monitoring_settings_frame = ctk.CTkFrame(
            self.manager_tab_frame
        )  # Pai agora é manager_tab_frame
        self.monitoring_settings_frame.pack(fill="x", pady=(0, 10))
        # ... (seu auto_start_monitoring_checkbox e monitoring_status_label como antes) ...
        self.auto_start_monitoring_checkbox = ctk.CTkCheckBox(
            self.monitoring_settings_frame,
            text="Ativar monitoramento automático ao iniciar o programa",
        )
        self.auto_start_monitoring_checkbox.pack(side="left", padx=5, pady=5)

        self.start_with_windows_checkbox = ctk.CTkCheckBox(
            self.monitoring_settings_frame,
            text="Iniciar com o Windows",
            command=self.toggle_startup_status,  # Comando para aplicar a mudança
        )
        self.start_with_windows_checkbox.pack(side="left", padx=(20, 5), pady=5)

        self.monitoring_interval_label = ctk.CTkLabel(
            self.monitoring_settings_frame, text="Intervalo (segundos):"
        )
        self.monitoring_interval_label.pack(side="left", padx=(20, 2), pady=5)

        self.monitoring_interval_entry = ctk.CTkEntry(
            self.monitoring_settings_frame,
            width=60,  # Ajuste a largura conforme necessário
        )
        self.monitoring_interval_entry.pack(side="left", padx=(0, 10), pady=5)
        # Definiremos o valor inicial em load_app_data

        self.monitoring_status_label = ctk.CTkLabel(
            self.monitoring_settings_frame, text="Monitoramento Automático: Parado"
        )
        self.monitoring_status_label.pack(side="left", padx=10, pady=5)

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

        # Opcional: Iniciar minimizado (pode ser uma configuração no futuro)
        # if self.settings.get("start_minimized_to_tray", False): # Exemplo
        #     self.hide_to_tray()

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
        # ...
        try:
            icon_path = resource_path("CleanUnreal.ico")  # <--- USO DA FUNÇÃO AQUI
            # Ou, se você tiver uma pasta 'assets':
            # icon_path = resource_path(os.path.join("assets", "app_icon.png"))

            if os.path.exists(icon_path):
                self.icon_image = Image.open(icon_path)
            else:
                print(f"AVISO: Arquivo de ícone '{icon_path}' não encontrado.")
                self.icon_image = None
        except Exception as e:
            print(f"Erro ao carregar imagem do ícone: {e}")
            self.icon_image = None
        # ... resto da função setup_and_run_tray_icon

        # Define o menu da bandeja
        menu_items = (
            pystray.MenuItem(
                "Abrir Limpador", self.show_from_tray, default=True
            ),  # default=True faz ser a ação do duplo clique
            pystray.MenuItem("Monitoramento", self.create_monitoring_submenu()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Fechar Limpador", self.quit_application),
        )

        self.tray_icon = pystray.Icon(
            "LimpadorUnreal",
            icon=self.icon_image,
            title="Limpador de Cache Unreal",
            menu=menu_items,
        )

        # pystray.Icon.run() é bloqueante, então rodamos em uma thread separada
        # para que a UI do CustomTkinter continue funcionando.
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()
        print("UI: Ícone da bandeja configurado e thread iniciada.")

    def create_monitoring_submenu(self):
        """Cria o submenu para controle de monitoramento."""
        # Esta função é chamada para construir o submenu dinamicamente se necessário,
        # ou pode retornar um menu estático cujas ações verificam o estado.
        # Para simplicidade, vamos usar ações que verificam o estado atual.

        # Se quiséssemos texto dinâmico tipo "Parar Monitoramento (Ativo)"
        # precisaríamos atualizar o menu do ícone, o que é mais complexo.
        # Vamos usar uma única ação "Alternar Monitoramento".
        return pystray.Menu(
            pystray.MenuItem(
                "Alternar Monitoramento", self.toggle_monitoring_from_tray
            ),
            pystray.MenuItem(
                lambda text: f"Status: {'Ativo' if self.monitoring_thread and self.monitoring_thread.is_alive() else 'Parado'}",
                action=None,
                enabled=False,
            ),  # Apenas informativo, não clicável
        )

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
        self.global_status_label.configure(
            text="Status Global: Iniciando limpeza de projetos permitidos..."
        )
        cleaned_count = 0
        total_space_freed_overall = 0

        if not self.project_widgets:
            self.global_status_label.configure(
                text="Status Global: Nenhum projeto na lista para limpar."
            )
            return

        for widget_info in self.project_widgets:
            project_data = widget_info["data"]
            project_path = project_data["path"]
            project_name = project_data["name"]
            allow_clean_cb = widget_info["allow_clean_checkbox"]
            cache_label = widget_info["cache_info_label"]

            if allow_clean_cb.get() == 1:
                self.after(
                    0,
                    self._update_cache_info_label,
                    cache_label,
                    "Cache: Verificando para limpeza...",
                )
                if is_unreal_project_open(project_path):
                    print(
                        f"UI Global Clean: Projeto {project_name} está aberto. Pulando."
                    )
                    self.after(
                        0,
                        self._update_cache_info_label,
                        cache_label,
                        "Cache: (Pulado - Projeto Aberto)",
                    )
                    continue

                # Inicia a thread de limpeza para este projeto
                # Precisamos de uma maneira de saber quando todas as threads terminarem para o status global
                # Por agora, vamos limpar sequencialmente para simplificar o feedback global.
                # Para limpeza em threads separadas, o feedback global seria mais complexo.

                print(f"UI Global Clean: Limpando {project_name}...")
                self.after(
                    0, self._update_cache_info_label, cache_label, "Cache: Limpando..."
                )

                # Chamada síncrona para a lógica de limpeza para este exemplo simplificado de botão global
                # Idealmente, isso também seria em thread para não bloquear a UI se muitos projetos.
                # Para este botão global, talvez um feedback "Limpando projeto X..." seja suficiente.
                space_freed, cleaned_folders, errors = clean_project_cache(
                    project_path, self
                )

                if errors:
                    msg = f"Limpeza Parcial. Liberado: {format_size(space_freed)}."
                elif cleaned_folders:
                    msg = f"Limpo! Liberado: {format_size(space_freed)}."
                    cleaned_count += 1
                    total_space_freed_overall += space_freed
                else:
                    msg = "Nada para limpar."
                self.after(0, self._update_cache_info_label, cache_label, msg)

                # Re-verificar o tamanho
                if cleaned_folders:
                    new_size_bytes = calculate_project_cache_size(project_path)
                    self.after(
                        0,
                        self._update_cache_info_label,
                        cache_label,
                        f"Cache Agora: {format_size(new_size_bytes)}",
                    )
            else:
                print(f"UI Global Clean: Limpeza não permitida para {project_name}.")
                # self.after(0, self._update_cache_info_label, cache_label, "Cache: (Limpeza não permitida)") # Opcional

        final_status = f"Status Global: Concluído. {cleaned_count} projeto(s) limpo(s)."
        if total_space_freed_overall > 0:
            final_status += (
                f" Total liberado: {format_size(total_space_freed_overall)}."
            )
        self.global_status_label.configure(text=final_status)

    def load_app_data(self):
        self.log_message("UI: Carregando dados do aplicativo...")
        default_interval = 3600  # Valor padrão de 1 hora em segundos
        loaded_interval = default_interval

        try:
            if os.path.exists(ABSOLUTE_CONFIG_PATH):
                with open(ABSOLUTE_CONFIG_PATH, "r") as f:
                    data = json.load(f)

                # Carrega configurações de monitoramento
                saved_projects = data.get("projects", [])
                settings = data.get("settings", {})

                for i, project_data_from_json in enumerate(saved_projects):
                    project_name = project_data_from_json.get(
                        "name", "NOME_AUSENTE_JSON"
                    )
                    project_path_from_json = project_data_from_json.get("path")

                    self.log_message(
                        f"Processando projeto salvo {i+1}/{len(saved_projects)}: '{project_name}' com path '{project_path_from_json}'",
                        level="DEBUG",
                    )

                    if not project_path_from_json:
                        self.log_message(
                            f"Projeto salvo '{project_name}' não tem caminho. Pulando.",
                            level="WARNING",
                        )
                        continue

                    # Normalizar o caminho do JSON para comparação e uso consistente
                    normalized_path_from_json = os.path.normpath(project_path_from_json)
                    print(
                        f"--- DEBUG (load_app_data): Path normalizado do JSON para '{project_name}': {normalized_path_from_json}"
                    )

                    # Verifica se este caminho normalizado já está nos caminhos exibidos
                    # (displayed_project_paths também deveria idealmente armazenar caminhos normalizados)
                    if normalized_path_from_json not in self.displayed_project_paths:
                        self.log_message(
                            f"'{project_name}' (path: {normalized_path_from_json}) NÃO está em displayed_project_paths. Tentando adicionar à UI...",
                            level="DEBUG",
                        )

                        # Atualiza o project_data com o caminho normalizado para consistência interna
                        project_data_to_add = (
                            project_data_from_json.copy()
                        )  # Evita modificar o dict original se não necessário
                        project_data_to_add["path"] = normalized_path_from_json

                        self.add_project_entry_to_ui(
                            project_data_to_add, from_saved_data=True
                        )
                        self.displayed_project_paths.add(
                            normalized_path_from_json
                        )  # Adiciona o caminho normalizado
                        self.log_message(
                            f"'{project_name}' adicionado a displayed_project_paths. Total agora: {len(self.displayed_project_paths)}",
                            level="DEBUG",
                        )
                    else:
                        self.log_message(
                            f"'{project_name}' (path: {normalized_path_from_json}) JÁ ESTÁ em displayed_project_paths. Pulando adição à UI aqui.",
                            level="DEBUG",
                        )

                self.log_message(
                    f"{len(self.project_widgets)} projetos agora na UI após carregar do JSON."
                )  # Conta os widgets reais

                if settings.get("auto_start_monitoring_on_launch", False):
                    self.auto_start_monitoring_checkbox.select()
                else:
                    self.auto_start_monitoring_checkbox.deselect()

                # --- CARREGAR INTERVALO DE MONITORAMENTO ---
                loaded_interval_str = settings.get(
                    "monitoring_interval_seconds", str(default_interval)
                )
                try:
                    loaded_interval = int(loaded_interval_str)
                    if loaded_interval <= 0:  # Garante que o intervalo seja positivo
                        loaded_interval = default_interval
                        self.log_message(
                            f"Intervalo de monitoramento inválido ('{loaded_interval_str}') carregado do JSON, usando padrão: {default_interval}s.",
                            level="WARNING",
                        )
                except ValueError:
                    loaded_interval = default_interval
                    self.log_message(
                        f"Valor do intervalo de monitoramento ('{loaded_interval_str}') não é um número, usando padrão: {default_interval}s.",
                        level="WARNING",
                    )
                # -----------------------------------------

                saved_projects = data.get("projects", [])
                # ... (resto do carregamento dos projetos como antes) ...

                self.log_message(
                    f"{len(saved_projects)} projetos e configurações carregados."
                )
            else:
                self.log_message(
                    f"UI: Tentando carregar dados de: {ABSOLUTE_CONFIG_PATH}",
                    level="DEBUG",
                )  # Log com o caminho absoluto
                # Configurações padrão se o arquivo não existe
                self.auto_start_monitoring_checkbox.deselect()

        except Exception as e:
            self.log_message(
                f"Erro ao carregar dados de {ABSOLUTE_CONFIG_PATH}: {e}", level="ERROR"
            )
            # Reseta para padrões em caso de erro grave ao carregar
            self.auto_start_monitoring_checkbox.deselect()

        # Define o valor no campo de entrada e na variável da instância
        self.AUTO_MONITOR_INTERVAL_SECONDS = loaded_interval
        self.monitoring_interval_entry.delete(0, "end")
        self.monitoring_interval_entry.insert(
            0, str(self.AUTO_MONITOR_INTERVAL_SECONDS)
        )
        self.log_message(
            f"Intervalo de monitoramento definido para: {self.AUTO_MONITOR_INTERVAL_SECONDS} segundos.",
            level="DEBUG",
        )

    def save_app_data(self):
        print("--- DEBUG: save_app_data() FOI CHAMADO ---")

        # ... (prints de depuração iniciais e obtenção do current_working_dir como antes) ...

        self.log_message("UI: Preparando dados para salvar...", level="DEBUG")
        data_to_save = {"projects": [], "settings": {}}

        # --- SALVAR CONFIGURAÇÕES DE MONITORAMENTO E INTERVALO ---
        auto_start_on_launch = False
        if hasattr(
            self, "auto_start_monitoring_checkbox"
        ):  # Verifica se o atributo existe
            auto_start_on_launch = self.auto_start_monitoring_checkbox.get() == 1
        self.log_message(
            f"UI: Tentando salvar dados em: {ABSOLUTE_CONFIG_PATH}", level="DEBUG"
        )  # Log com o caminho absoluto
        current_interval_str = str(self.AUTO_MONITOR_INTERVAL_SECONDS)  # Valor padrão
        if hasattr(self, "monitoring_interval_entry"):
            try:
                # Pega o valor do campo, valida se é inteiro e positivo
                entry_val = self.monitoring_interval_entry.get()
                parsed_interval = int(entry_val)
                if parsed_interval > 0:
                    current_interval_str = str(parsed_interval)
                    # Atualiza a variável da instância também, para consistência imediata
                    self.AUTO_MONITOR_INTERVAL_SECONDS = parsed_interval
                else:
                    self.log_message(
                        f"Valor de intervalo inválido no campo: '{entry_val}'. Salvando o valor anterior/padrão: {self.AUTO_MONITOR_INTERVAL_SECONDS}",
                        level="WARNING",
                    )
            except ValueError:
                self.log_message(
                    f"Valor de intervalo não numérico no campo: '{self.monitoring_interval_entry.get()}'. Salvando o valor anterior/padrão: {self.AUTO_MONITOR_INTERVAL_SECONDS}",
                    level="WARNING",
                )

        data_to_save["settings"][
            "auto_start_monitoring_on_launch"
        ] = auto_start_on_launch
        data_to_save["settings"]["monitoring_interval_seconds"] = current_interval_str

        current_working_dir = ""  # Inicializa para o caso de getcwd() falhar
        try:
            current_working_dir = os.getcwd()
            print(
                f"--- DEBUG: Diretório de trabalho atual (onde tentará salvar): {current_working_dir} ---"
            )
        except Exception as e_getcwd:
            print(f"--- DEBUG: Erro ao obter diretório de trabalho: {e_getcwd} ---")

        # Seus prints de depuração anteriores para o conteúdo de self.project_widgets podem ficar aqui
        print(
            f"Conteúdo de self.project_widgets ({len(self.project_widgets)} itens) ANTES de salvar:"
        )
        for i, widget_info_item in enumerate(
            self.project_widgets
        ):  # Corrigido para widget_info_item
            p_data = widget_info_item.get("data", {})
            verify_cb = widget_info_item.get("verify_auto_checkbox")
            allow_cb = widget_info_item.get("allow_clean_checkbox")
            gb_entry = widget_info_item.get("gb_limit_entry")

            monitor_auto_val = verify_cb.get() == 1 if verify_cb else "N/A"
            allow_clean_val = allow_cb.get() == 1 if allow_cb else "N/A"
            gb_limit_val = gb_entry.get() if gb_entry else "N/A"

            print(
                f"  Item {i}: Name: {p_data.get('name')}, Path: {p_data.get('path')}, UProject: {p_data.get('uproject_file')}"
            )
            print(
                f"    MonitorAuto: {monitor_auto_val}, AllowClean: {allow_clean_val}, GBLimit: '{gb_limit_val}'"
            )

        print("UI: Preparando dados para salvar...")
        data_to_save = {"projects": [], "settings": {}}

        # Salva configuração de monitoramento
        if hasattr(
            self, "auto_start_monitoring_checkbox"
        ):  # Verifica se o atributo existe
            data_to_save["settings"]["auto_start_monitoring_on_launch"] = (
                self.auto_start_monitoring_checkbox.get() == 1
            )
        else:
            data_to_save["settings"][
                "auto_start_monitoring_on_launch"
            ] = False  # Valor padrão

        # Salva dados dos projetos
        for widget_info_item in self.project_widgets:
            project_data = widget_info_item["data"]

            # Pega os widgets do dicionário de forma segura
            verify_auto_checkbox = widget_info_item.get("verify_auto_checkbox")
            allow_clean_checkbox = widget_info_item.get("allow_clean_checkbox")
            gb_limit_entry = widget_info_item.get("gb_limit_entry")

            project_config = {
                "path": project_data.get(
                    "path", "CAMINHO_AUSENTE"
                ),  # .get() para segurança
                "name": project_data.get("name", "NOME_AUSENTE"),
                "uproject_file": project_data.get("uproject_file", ""),
                "monitor_auto": (
                    verify_auto_checkbox.get() == 1 if verify_auto_checkbox else False
                ),
                "allow_clean": (
                    allow_clean_checkbox.get() == 1 if allow_clean_checkbox else False
                ),
                "gb_limit": gb_limit_entry.get() if gb_limit_entry else "",
            }
            data_to_save["projects"].append(project_config)

        config_file_path = ""
        if (
            current_working_dir
        ):  # Só tenta construir o caminho completo se current_working_dir não for vazio
            config_file_path = os.path.join(current_working_dir, CONFIG_FILE_NAME)

        try:
            if not config_file_path:
                # Se não conseguimos determinar o current_working_dir, não tentamos salvar.
                # Isso é improvável, mas é uma checagem de segurança.
                print(
                    f"--- ERRO FATAL AO SALVAR: Caminho do arquivo de configuração não pôde ser determinado. ---"
                )
                return

            print(f"UI: Tentando salvar dados em: {config_file_path}")
            with open(ABSOLUTE_CONFIG_PATH, "w") as f:
                json.dump(data_to_save, f, indent=4)
            print(f"UI: Dados salvos com sucesso em {config_file_path}.")
            self.log_message(f"UI: Dados salvos com sucesso em {ABSOLUTE_CONFIG_PATH}.")
            # print(f"DEBUG: Conteúdo que FOI salvo: {json.dumps(data_to_save, indent=4)}") # Print opcional do conteúdo salvo
        except Exception as e:
            print(f"--- ERRO FATAL AO SALVAR DADOS em '{config_file_path}': {e} ---")
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
        """Função que roda na thread para calcular o tamanho do cache."""
        try:
            size_bytes = calculate_project_cache_size(project_path)
            # Pede para a thread da UI atualizar o label
            self.after(
                0,
                self._update_cache_info_label,
                cache_info_label_widget,
                f"Cache: {format_size(size_bytes)}",
            )
        except Exception as e:
            print(f"Erro na thread de verificação de cache: {e}")
            self.after(
                0,
                self._update_cache_info_label,
                cache_info_label_widget,
                "Cache: Erro ao verificar",
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
        """
        Atualiza a interface com a lista de projetos da DESCOBERTA AUTOMÁTICA.
        Esta função SEMPRE deve ser chamada pela thread principal da UI (usando self.after).
        """

        print(
            f"DEBUG: update_project_list_ui_from_discovery INÍCIO - project_widgets: {[p['data']['name'] for p in self.project_widgets]}"
        )
        print(
            f"DEBUG: update_project_list_ui_from_discovery INÍCIO - displayed_project_paths: {self.displayed_project_paths}"
        )
        print(
            f"DEBUG: update_project_list_ui_from_discovery recebendo projects_data: {[p['name'] for p in projects_data] if projects_data else 'Nenhum'}"
        )

        if error_message:
            # CORRIGIDO AQUI:
            self.global_status_label.configure(
                text=f"Status Global: Erro na descoberta - {error_message}"
            )
            # Opcional: ainda mostrar erro na lista de projetos se desejar
            # error_label = ctk.CTkLabel(self.project_scrollable_frame, text=error_message, text_color="red")
            # error_label.pack(pady=10)
            # self.project_widgets.append({"frame": error_label}) # Se adicionar, lembre-se de limpar em _clear_project_list_ui
            return

        print(
            f"DEBUG: update_project_list_ui_from_discovery FIM - project_widgets: {[p['data']['name'] for p in self.project_widgets]}"
        )
        print(
            f"DEBUG: update_project_list_ui_from_discovery FIM - displayed_project_paths: {self.displayed_project_paths}"
        )

        if not projects_data:
            # CORRIGIDO AQUI:
            self.global_status_label.configure(
                text="Status Global: Nenhum novo projeto encontrado na busca automática."
            )
            # Opcional: Mensagem na lista de projetos se ela estiver vazia e nenhuma outra mensagem estiver lá
            # if not self.project_widgets: # Só mostra se a lista estiver realmente vazia
            #     no_projects_label = ctk.CTkLabel(self.project_scrollable_frame, text="Nenhum projeto encontrado no caminho padrão.")
            #     no_projects_label.pack(pady=10)
            #     self.project_widgets.append({"frame": no_projects_label})
            return

        # CORRIGIDO AQUI:
        # Atualiza o status global para refletir o resultado da última operação de descoberta.
        # Se estamos adicionando a uma lista existente (clear_current_list=False),
        # o número de projetos 'encontrados' nesta chamada específica é o que importa para a mensagem.
        self.global_status_label.configure(
            text=f"Status Global: {len(projects_data)} projeto(s) econtrado(s)/processado(s) na última busca."
        )

        added_now_count = 0
        for project_info in projects_data:
            # A verificação de duplicidade e adição à UI é feita por add_project_entry_to_ui
            # e pelo controle de self.displayed_project_paths lá e em load_app_data.
            # Aqui, apenas garantimos que chamamos a adição para cada projeto retornado pela descoberta.
            # Se o projeto já existe em self.displayed_project_paths, add_project_entry_to_ui (se from_saved_data=False) não o adicionará visualmente.
            if project_info["path"] not in self.displayed_project_paths:
                self.add_project_entry_to_ui(
                    project_info, from_saved_data=False
                )  # from_saved_data é False para descobertas novas
                # self.displayed_project_paths.add(project_info["path"]) # Isso agora é feito dentro de add_project_entry_to_ui
                added_now_count += 1

        if added_now_count > 0:
            self.global_status_label.configure(
                text=f"Status Global: {added_now_count} novo(s) projeto(s) adicionado(s) da pasta padrão."
            )
        elif not projects_data:  # Se projects_data estava vazio
            self.global_status_label.configure(
                text="Status Global: Nenhum projeto encontrado na busca."
            )
        # Se projects_data não estava vazio mas added_now_count é 0, significa que todos já estavam na lista.
        # O status global já terá sido atualizado pelo carregamento inicial ou pela última operação.

    def add_project_entry_to_ui(self, project_info, from_saved_data=False):
        """
        Adiciona uma única entrada de projeto à UI.
        Se from_saved_data is True, preenche os controles com os valores de project_info.
        """
        # Garante que o projeto não seja adicionado visualmente mais de uma vez
        if project_info["path"] in self.displayed_project_paths and not from_saved_data:
            print(
                f"UI: Projeto {project_info['name']} já exibido, pulando adição visual duplicada."
            )
            return

        print(f"--- Adicionando UI para: {project_info['name']} ---")
        project_name = project_info["name"]

        project_entry_frame = ctk.CTkFrame(
            self.project_scrollable_frame, fg_color=("gray80", "gray25")
        )
        project_entry_frame.pack(fill="x", pady=5, padx=5)

        top_line_frame = ctk.CTkFrame(project_entry_frame, fg_color="transparent")
        top_line_frame.pack(fill="x", padx=5, pady=(5, 0))
        project_label = ctk.CTkLabel(
            top_line_frame,
            text=project_name,
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        )
        project_label.pack(side="left", padx=(5, 5))
        cache_info_label = ctk.CTkLabel(top_line_frame, text="Cache: -", anchor="e")
        cache_info_label.pack(side="right", padx=(5, 5))

        controls_line_frame = ctk.CTkFrame(project_entry_frame, fg_color="transparent")
        controls_line_frame.pack(
            fill="x", padx=5, pady=(0, 5)
        )  # Aumentei pady inferior

        verify_auto_label = ctk.CTkLabel(controls_line_frame, text="Monitorar Auto:")
        verify_auto_label.pack(side="left", padx=(5, 2))
        verify_auto_checkbox = ctk.CTkCheckBox(controls_line_frame, text="", width=20)
        verify_auto_checkbox.pack(side="left", padx=(0, 10))

        allow_clean_label = ctk.CTkLabel(controls_line_frame, text="Permitir Limpeza:")
        allow_clean_label.pack(side="left", padx=(5, 2))
        allow_clean_checkbox = ctk.CTkCheckBox(controls_line_frame, text="", width=20)
        allow_clean_checkbox.pack(side="left", padx=(0, 10))

        gb_limit_label = ctk.CTkLabel(controls_line_frame, text="Limite GB (Auto):")
        gb_limit_label.pack(side="left", padx=(5, 2))
        gb_limit_entry = ctk.CTkEntry(
            controls_line_frame, width=50, placeholder_text="Ex: 5"
        )
        gb_limit_entry.pack(side="left", padx=(0, 10))

        # Se carregando de dados salvos, preenche os controles
        if from_saved_data:
            if project_info.get("monitor_auto", False):
                verify_auto_checkbox.select()
            else:
                verify_auto_checkbox.deselect()

            if project_info.get(
                "allow_clean", False
            ):  # Default para False se não salvo antes
                allow_clean_checkbox.select()
            else:
                allow_clean_checkbox.deselect()

            gb_limit_val = project_info.get("gb_limit", "")
            if gb_limit_val:  # Evita inserir "None" como string
                gb_limit_entry.insert(0, gb_limit_val)

        widget_references = {
            "frame": project_entry_frame,
            "data": project_info,  # Contém path, name, e uproject_file se validado
            "name_label": project_label,
            "cache_info_label": cache_info_label,
            "verify_auto_checkbox": verify_auto_checkbox,
            "allow_clean_checkbox": allow_clean_checkbox,
            "gb_limit_entry": gb_limit_entry,
            # Botões removidos daqui
        }
        self.project_widgets.append(widget_references)
        if (
            not from_saved_data
        ):  # Adiciona ao set apenas se não veio de dados salvos (já foi adicionado em load_app_data)
            self.displayed_project_paths.add(project_info["path"])
            print(
                f"DEBUG: add_project_entry_to_ui (from_saved_data={from_saved_data}) ADICIONOU: {project_info['name']}"
            )
            print(
                f"DEBUG: add_project_entry_to_ui - project_widgets AGORA: {[p['data']['name'] for p in self.project_widgets]}"
            )
            print(
                f"DEBUG: add_project_entry_to_ui - displayed_project_paths AGORA: {self.displayed_project_paths}"
            )

    def _auto_monitoring_loop(self):
        """Loop principal que roda na thread de monitoramento."""
        print("Thread Monitoramento: Iniciada.")
        # Atualiza o label na UI via self.after para garantir que é feito na thread principal da UI
        self.after(
            0,
            self.monitoring_status_label.configure,
            {"text": "Monitoramento Automático: Ativo"},
        )

        while not self.monitoring_stop_event.is_set():
            print("Thread Monitoramento: Iniciando ciclo de verificação...")
            self.after(
                0,
                self.monitoring_status_label.configure,
                {"text": "Monitoramento Automático: Verificando..."},
            )

            for project_widget_info in self.project_widgets:
                if self.monitoring_stop_event.is_set():
                    break

                project_data = project_widget_info["data"]
                project_path = project_data["path"]
                project_name = project_data["name"]

                monitor_auto_checkbox = project_widget_info.get("verify_auto_checkbox")
                allow_clean_checkbox = project_widget_info.get("allow_clean_checkbox")
                gb_limit_entry = project_widget_info.get("gb_limit_entry")
                cache_info_label = project_widget_info.get("cache_info_label")

                if not (
                    monitor_auto_checkbox
                    and allow_clean_checkbox
                    and gb_limit_entry
                    and cache_info_label
                ):
                    print(
                        f"Thread Monitoramento: Widgets faltando para o projeto {project_name}, pulando."
                    )
                    continue

                if monitor_auto_checkbox.get() == 1 and allow_clean_checkbox.get() == 1:
                    print(
                        f"Thread Monitoramento: Verificando {project_name} (Monitorar e Permitir Limpeza ON)"
                    )

                    if is_unreal_project_open(project_path):
                        print(
                            f"Thread Monitoramento: {project_name} está aberto, pulando limpeza."
                        )
                        self.after(
                            0,
                            self._update_cache_info_label,
                            cache_info_label,
                            f"Cache: (Auto: Pulado - Aberto)",
                        )
                        continue

                    gb_limit_str = gb_limit_entry.get()
                    if not gb_limit_str:
                        print(
                            f"Thread Monitoramento: Limite GB não definido para {project_name}, pulando."
                        )
                        self.after(
                            0,
                            self._update_cache_info_label,
                            cache_info_label,
                            f"Cache: (Auto: Sem Limite GB)",
                        )
                        continue

                    try:
                        gb_limit_float = float(gb_limit_str)
                        limit_bytes = gb_limit_float * (1024**3)
                    except ValueError:
                        print(
                            f"Thread Monitoramento: Limite GB inválido ('{gb_limit_str}') para {project_name}, pulando."
                        )
                        self.after(
                            0,
                            self._update_cache_info_label,
                            cache_info_label,
                            f"Cache: (Auto: Limite GB Inválido)",
                        )
                        continue

                    current_cache_size_bytes = calculate_project_cache_size(
                        project_path
                    )
                    print(
                        f"Thread Monitoramento: {project_name} - Cache Atual: {format_size(current_cache_size_bytes)}, Limite: {format_size(limit_bytes)}"
                    )

                    if current_cache_size_bytes > limit_bytes:
                        print(
                            f"Thread Monitoramento: {project_name} excedeu o limite! Tentando limpar..."
                        )
                        self.after(
                            0,
                            self._update_cache_info_label,
                            cache_info_label,
                            "Cache: (Auto Limpeza...)",
                        )

                        space_freed, cleaned, errors = clean_project_cache(
                            project_path, self
                        )

                        if errors:
                            msg = f"Auto Limpeza Parcial. Liberado: {format_size(space_freed)}."
                        elif cleaned:  # 'cleaned' aqui é a lista de pastas limpas
                            msg = f"Auto Limpo! Liberado: {format_size(space_freed)}."
                        else:
                            msg = "Auto: Nada para limpar."
                        self.after(
                            0, self._update_cache_info_label, cache_info_label, msg
                        )

                        if cleaned:  # Se algo foi limpo
                            new_size_bytes = calculate_project_cache_size(project_path)
                            self.after(
                                0,
                                self._update_cache_info_label,
                                cache_info_label,
                                f"Cache Agora: {format_size(new_size_bytes)}",
                            )
                    else:
                        self.after(
                            0,
                            self._update_cache_info_label,
                            cache_info_label,
                            f"Cache: {format_size(current_cache_size_bytes)} (Auto OK)",
                        )
                else:
                    if monitor_auto_checkbox.get() == 1:
                        print(
                            f"Thread Monitoramento: {project_name} - Monitorar ON, Permitir Limpeza OFF. Apenas verificando."
                        )
                        current_cache_size_bytes = calculate_project_cache_size(
                            project_path
                        )
                        self.after(
                            0,
                            self._update_cache_info_label,
                            cache_info_label,
                            f"Cache: {format_size(current_cache_size_bytes)} (Auto Monitorado)",
                        )

            if (
                self.monitoring_stop_event.is_set()
            ):  # Verifica novamente antes de dormir
                break

            self.after(
                0,
                self.monitoring_status_label.configure,
                {"text": f"Monitoramento Automático: Aguardando..."},
            )
            stopped_early = self.monitoring_stop_event.wait(
                timeout=self.AUTO_MONITOR_INTERVAL_SECONDS
            )
            if stopped_early:
                break

        print("Thread Monitoramento: Parada.")

        # Função interna para garantir que a atualização do label ocorra na thread principal
        def update_label_to_stopped_final():
            print(
                "--- DEBUG: update_label_to_stopped_final EXECUTADA pela thread da UI ---"
            )
            if (
                hasattr(self, "monitoring_status_label")
                and self.monitoring_status_label.winfo_exists()
            ):
                self.monitoring_status_label.configure(
                    text="Monitoramento Automático: Parado"
                )
                print(
                    "--- DEBUG: Label de monitoramento ATUALIZADO para 'Parado' pela thread do monitor. ---"
                )
            else:
                print(
                    "--- DEBUG: Label de monitoramento não pôde ser atualizado para 'Parado' (não existe/destruído). ---"
                )

        self.after(0, update_label_to_stopped_final)  # Agenda a atualização

    def start_auto_monitoring(self):
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            print("UI: Monitoramento já está ativo.")
            return

        self.monitoring_stop_event.clear()  # Reseta o evento de parada
        self.monitoring_thread = threading.Thread(target=self._auto_monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()

        self.monitoring_status_label.configure(text="Monitoramento Automático: Ativo")
        # Linhas removidas que alteravam o estado dos botões manuais de start/stop
        print("UI: Monitoramento automático iniciado.")

    def stop_auto_monitoring(self):
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            print("UI: Solicitando parada do monitoramento...")
            self.monitoring_status_label.configure(
                text="Monitoramento Automático: Parando..."
            )  # Atualiza o status primeiro
            self.monitoring_stop_event.set()  # Sinaliza para a thread parar
            # A própria thread _auto_monitoring_loop atualizará o label para "Parado" quando sair.
            # E não há mais botões de start/stop para reabilitar aqui.
        else:
            print("UI: Monitoramento não estava ativo ou já foi parado.")
            self.monitoring_status_label.configure(
                text="Monitoramento Automático: Parado"
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
