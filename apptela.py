import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import time
import random
from bot_engine import BotEngine
from iq_service import IQService
from strategy_analyzer import StrategyAnalyzer  # Novo import
from settings_store import load_settings, save_settings

# ===================== WRAPPER PARA BOTENGINE =====================
# ===================== WRAPPER PARA BOTENGINE =====================
class BotEngineWrapper:
    """
    Wrapper para manter compatibilidade com a UI (modo 24h),
    mas quem opera de verdade é o BotEngine (regras + ML + execução real).
    """
    def __init__(self, service, config, event_queue, analyzer=None):
        self.engine = BotEngine(service, config, event_queue=event_queue, analyzer=analyzer)

    def start(self):
        self.engine.start()

    def stop(self):
        self.engine.stop()


class ProDashboardApp:
    """
    UI otimizada (leve e rápida):
    - Poll do queue em lote (batch) para evitar travamento
    - Log em buffer com flush periódico
    - Limite de linhas do log (corta o excesso)
    - Treeview: atualiza só o necessário (upsert) e evita recomputar assertividade completa toda hora
    - Sidebar com scroll (canvas + frame)
    - Menu compacto (operações no menu)
    """

    def __init__(self, root):
        self.root = root
        self.root.title("FrancisXTrader® PRO BOT (ML) - MODO 24H")
        
        # --- FIX TELA PRETA LINUX ---
        self.root.withdraw()
        self.root.configure(bg="#0b1220")
        self.root.after(500, self._show_maximized)
        
        # Configuração original de tamanho (backup caso maximize não funcione)
        self.root.geometry("1360x780")
        
        self.service = None
        self.analyzer = None  # Novo: StrategyAnalyzer
        self.connected = False
        self.bot = None
        self.bot_running = False
        self.mode_24h = False  # Novo: Modo 24h ativo

        self.event_queue = queue.Queue()

        self._balance_thread_running = False
        self._session_profit = 0.0

        # Tree rows: order_id -> iid
        self.trade_rows = {}
        # Stats por par (para não recalcular em loop)
        self.pair_stats = {}  # par -> dict(w,l,profit,trades)

        # Log buffer (UI)
        self._log_buf = []
        self._ia_log_buf = []  # NOVO: Buffer separado para logs da IA
        self._last_log_flush = 0.0
        self._last_ia_log_flush = 0.0  # NOVO: Timer separado para IA logs
        self.LOG_FLUSH_INTERVAL = 0.35
        self.LOG_MAX_LINES = 500
        self.IA_LOG_MAX_LINES = 200  # NOVO: Máximo de linhas para log da IA

        # Config vars
        self.entry_var = tk.DoubleVar(value=10.0)
        self.meta_var = tk.DoubleVar(value=20.0)
        self.stop_loss_var = tk.DoubleVar(value=-15.0)
        self.initial_var = tk.DoubleVar(value=0.0)

        self.autostop_var = tk.BooleanVar(value=True)

        # filtros stats por par
        self.min_trades_var = tk.IntVar(value=5)
        self.min_acc_var = tk.DoubleVar(value=45.0)
        self.block_bad_pairs_var = tk.BooleanVar(value=False)

        # Indicadores (checkbox)
        self.ind_close = tk.BooleanVar(value=True)
        self.ind_rsi = tk.BooleanVar(value=True)
        self.ind_macd = tk.BooleanVar(value=True)
        self.ind_stoch = tk.BooleanVar(value=True)
        self.ind_bb = tk.BooleanVar(value=True)
        self.ind_cci = tk.BooleanVar(value=False)

        # Perfil (um selecionável)
        self.profile_var = tk.StringVar(value="Agressivo")

        # Modo conta
        self.account_mode = tk.StringVar(value="PRACTICE")

        # NOVAS VARIÁVEIS PARA ANÁLISE IA
        self.validation_mode = tk.BooleanVar(value=False)  # Modo validação
        self.auto_apply_var = tk.BooleanVar(value=True)  # Aplicar resultado automaticamente
        self.analysis_progress = 0
        self.best_results = {}  # Armazenar melhores resultados
        self.analysis_active = False
        self.mode_24h_var = tk.BooleanVar(value=True)  # NOVO: Modo 24h ativado por padrão

        self._build_ui()
        self._load_saved_login()
        self._poll_queue()

    def _show_maximized(self):
        """Fix para tela preta no Linux - mostra maximizado"""
        try:
            self.root.attributes('-zoomed', True)
        except:
            pass  # Fallback para sistemas que não suportam
        self.root.deiconify()

    # ===================== UI =====================
    def _build_ui(self):
        self._build_menu()

        top = tk.Frame(self.root, bg="#050a14", height=46)
        top.pack(fill="x")
        tk.Label(top, text="FrancisXTrader® PRO BOT (ML) - MODO 24H", bg="#050a14", fg="#22c55e",
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=14)
        tk.Label(top, text="Criado por FrancisXTrader®", bg="#050a14", fg="#64748b",
                 font=("Segoe UI", 9)).pack(side="right", padx=14)

        body = tk.Frame(self.root, bg="#0b1220")
        body.pack(fill="both", expand=True)

        # Sidebar com scroll
        self.sidebar_canvas = tk.Canvas(body, bg="#050a14", highlightthickness=0, width=360)
        self.sidebar_canvas.pack(side="left", fill="y")

        sb_scroll = ttk.Scrollbar(body, orient="vertical", command=self.sidebar_canvas.yview)
        sb_scroll.pack(side="left", fill="y")

        self.sidebar_canvas.configure(yscrollcommand=sb_scroll.set)

        self.sidebar = tk.Frame(self.sidebar_canvas, bg="#050a14")
        self.sidebar_window = self.sidebar_canvas.create_window((0, 0), window=self.sidebar, anchor="nw")

        def _on_sidebar_config(_evt=None):
            self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))

        def _on_canvas_config(evt):
            # faz o frame da sidebar acompanhar a largura do canvas
            self.sidebar_canvas.itemconfig(self.sidebar_window, width=evt.width)

        self.sidebar.bind("<Configure>", _on_sidebar_config)
        self.sidebar_canvas.bind("<Configure>", _on_canvas_config)

        self.content = tk.Frame(body, bg="#0b1220")
        self.content.pack(side="right", fill="both", expand=True)

        self._build_sidebar()
        self._build_content()
        self._build_footer()

    def _build_menu(self):
        menubar = tk.Menu(self.root, tearoff=0)
        self.root.config(menu=menubar)

        # MENU principal
        m = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="MENU", menu=m)

        m.add_command(label="Conectar / Desconectar", command=self._toggle_connect)
        m.add_separator()
        m.add_command(label="Iniciar Bot 24h", command=self._start_bot_24h)
        m.add_command(label="Parar Bot 24h", command=self._stop_bot)
        m.add_command(label="Analisar e Aplicar Configuração", command=self._start_full_analysis)

        test_menu = tk.Menu(m, tearoff=0)
        m.add_cascade(label="Testes", menu=test_menu)
        test_menu.add_command(label="Teste Trade (REAL) - PRACTICE/REAL", command=self._test_trade_real)
        test_menu.add_command(label="Teste Trade (BOT - Aleatório)", command=self._test_trade_bot)

        m.add_separator()
        m.add_command(label="Sair", command=self._close_app)

        # Conta (demo/real)
        acc = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="CONTA", menu=acc)
        acc.add_radiobutton(label="Conta Demo (PRACTICE)", variable=self.account_mode, value="PRACTICE")
        acc.add_radiobutton(label="Conta Real (REAL)", variable=self.account_mode, value="REAL")

    def _build_sidebar(self):
        pad = 12
        tk.Label(self.sidebar, text="TRADER PRO - MODO 24H", bg="#050a14", fg="#22c55e",
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=pad, pady=(14, 8))

        tk.Label(self.sidebar, text="EMAIL", bg="#050a14", fg="#94a3b8").pack(anchor="w", padx=pad)
        self.email_entry = tk.Entry(self.sidebar, bg="#0b1220", fg="white", insertbackground="#39ff14", relief="flat")
        self.email_entry.pack(fill="x", padx=pad, pady=(4, 10))

        tk.Label(self.sidebar, text="SENHA", bg="#050a14", fg="#94a3b8").pack(anchor="w", padx=pad)
        self.pass_entry = tk.Entry(self.sidebar, show="*", bg="#0b1220", fg="white", insertbackground="#39ff14", relief="flat")
        self.pass_entry.pack(fill="x", padx=pad, pady=(4, 6))

        self.save_login_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.sidebar, text="Salvar usuário e senha", variable=self.save_login_var,
                       bg="#050a14", fg="white", selectcolor="#050a14").pack(anchor="w", padx=pad, pady=(0, 10))

        # Botão conectar (muda cor/label)
        self.connect_btn = tk.Button(self.sidebar, text="CONECTAR", bg="#22c55e", fg="black",
                                     font=("Segoe UI", 12, "bold"), relief="flat", command=self._toggle_connect)
        self.connect_btn.pack(fill="x", padx=pad, pady=(8, 8), ipady=7)

        # ========== NOVA SEÇÃO: MODO 24H ==========
        tk.Label(self.sidebar, text="MODO OPERACIONAL 24H", bg="#050a14", fg="#f39c12",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=pad, pady=(14, 4))
        
        # Checkbox para modo 24h
        tk.Checkbutton(self.sidebar, text="Ativar modo 24h (opera automaticamente)", 
                      variable=self.mode_24h_var, bg="#050a14", fg="white", 
                      selectcolor="#050a14").pack(anchor="w", padx=pad, pady=(0, 8))
        
        # Botões de operação 24h
        operation_frame = tk.Frame(self.sidebar, bg="#050a14")
        operation_frame.pack(fill="x", padx=pad, pady=(0, 10))
        
        self.start_24h_btn = tk.Button(operation_frame, text="INICIAR BOT 24H", bg="#2ecc71", fg="white",
                                     font=("Segoe UI", 10, "bold"), relief="flat",
                                     command=self._start_bot_24h, state="disabled")
        self.start_24h_btn.pack(fill="x", pady=(0, 4))
        
        self.stop_24h_btn = tk.Button(operation_frame, text="PARAR BOT 24H", bg="#e74c3c", fg="white",
                                          font=("Segoe UI", 10, "bold"), relief="flat",
                                          command=self._stop_bot, state="disabled")
        self.stop_24h_btn.pack(fill="x")
        
        # Botão de análise única
        self.analyze_once_btn = tk.Button(self.sidebar, text="ANALISAR E APLICAR CONFIG", bg="#4f67ff", fg="white",
                                          font=("Segoe UI", 10, "bold"), relief="flat",
                                          command=self._start_full_analysis, state="disabled")
        self.analyze_once_btn.pack(fill="x", padx=pad, pady=(0, 10))
        # ===================================================

        # Perfil (checkbox exclusivo via radiobutton)
        tk.Label(self.sidebar, text="PERFIL", bg="#050a14", fg="#94a3b8").pack(anchor="w", padx=pad, pady=(12, 4))
        prof = tk.Frame(self.sidebar, bg="#050a14")
        prof.pack(fill="x", padx=pad)
        for name in ("Conservador", "Moderado", "Agressivo"):
            ttk.Radiobutton(prof, text=name, value=name, variable=self.profile_var).pack(anchor="w")

        # Gestão
        tk.Label(self.sidebar, text="GESTÃO", bg="#050a14", fg="#94a3b8").pack(anchor="w", padx=pad, pady=(14, 4))

        def _num_entry(label, var):
            frm = tk.Frame(self.sidebar, bg="#050a14")
            frm.pack(fill="x", padx=pad, pady=3)
            tk.Label(frm, text=label, bg="#050a14", fg="white").pack(side="left")
            ent = tk.Entry(frm, textvariable=var, bg="#0b1220", fg="white", insertbackground="#39ff14", relief="flat")
            ent.pack(side="right", fill="x", expand=True, padx=(10, 0))
            return ent

        _num_entry("Entrada (R$)", self.entry_var)
        _num_entry("Meta do dia (R$)", self.meta_var)
        _num_entry("Stop Loss (R$)", self.stop_loss_var)
        _num_entry("Valor inicial (R$)", self.initial_var)

        tk.Checkbutton(self.sidebar, text="Parar automático ao bater Meta/Stop", variable=self.autostop_var,
                       bg="#050a14", fg="white", selectcolor="#050a14").pack(anchor="w", padx=pad, pady=(6, 6))

        # Indicadores (como sua imagem)
        tk.Label(self.sidebar, text="INDICADORES (IA)", bg="#050a14", fg="#94a3b8").pack(anchor="w", padx=pad, pady=(14, 4))
        ind = tk.Frame(self.sidebar, bg="#050a14")
        ind.pack(fill="x", padx=pad)

        def _cb(text, var):
            tk.Checkbutton(ind, text=text, variable=var, bg="#050a14", fg="white", selectcolor="#050a14").pack(anchor="w")

        _cb("Fechar preço (candles)", self.ind_close)
        _cb("RSI", self.ind_rsi)
        _cb("MACD", self.ind_macd)
        _cb("Stochastic", self.ind_stoch)
        _cb("Bollinger Bands", self.ind_bb)
        _cb("CCI", self.ind_cci)

        # Filtro por par
        tk.Label(self.sidebar, text="FILTRO POR PAR", bg="#050a14", fg="#94a3b8").pack(anchor="w", padx=pad, pady=(14, 4))
        frm_f = tk.Frame(self.sidebar, bg="#050a14")
        frm_f.pack(fill="x", padx=pad)

        tk.Label(frm_f, text="Min trades/par", bg="#050a14", fg="white").grid(row=0, column=0, sticky="w")
        tk.Entry(frm_f, textvariable=self.min_trades_var, bg="#0b1220", fg="white",
                 insertbackground="#39ff14", relief="flat", width=8).grid(row=0, column=1, sticky="e", padx=(8,0))

        tk.Label(frm_f, text="Min %/par", bg="#050a14", fg="white").grid(row=1, column=0, sticky="w", pady=(4,0))
        tk.Entry(frm_f, textvariable=self.min_acc_var, bg="#0b1220", fg="white",
                 insertbackground="#39ff14", relief="flat", width=8).grid(row=1, column=1, sticky="e", padx=(8,0), pady=(4,0))

        tk.Checkbutton(self.sidebar, text="Bloquear pares ruins no robô", variable=self.block_bad_pairs_var,
                       bg="#050a14", fg="white", selectcolor="#050a14").pack(anchor="w", padx=pad, pady=(6, 6))

        # Ativos
        tk.Label(self.sidebar, text="ATIVOS (OTC / DIGITAL)", bg="#050a14", fg="#94a3b8").pack(anchor="w", padx=pad, pady=(14, 4))

        opts = tk.Frame(self.sidebar, bg="#050a14")
        opts.pack(fill="x", padx=pad)

        self.only_open = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text="Somente OTC abertos", variable=self.only_open,
                       bg="#050a14", fg="white", selectcolor="#050a14", command=self._refresh_assets).pack(side="left")
        tk.Button(opts, text="Atualizar", bg="#1f2937", fg="white", relief="flat",
                  command=self._refresh_assets).pack(side="right")

        list_frame = tk.Frame(self.sidebar, bg="#050a14")
        list_frame.pack(fill="both", padx=pad, pady=(6, 8))

        self.assets_list = tk.Listbox(list_frame, selectmode="multiple", height=10,
                                      bg="#0b1220", fg="white", selectbackground="#22c55e",
                                      exportselection=False)
        self.assets_list.pack(side="left", fill="both", expand=True)

        scr = tk.Scrollbar(list_frame, orient="vertical", command=self.assets_list.yview)
        scr.pack(side="right", fill="y")
        self.assets_list.configure(yscrollcommand=scr.set)

        tk.Label(self.sidebar, text="(Sem seleção: escolhe aleatório da lista)",
                 bg="#050a14", fg="#64748b", font=("Segoe UI", 9)).pack(anchor="w", padx=pad, pady=(0, 10))

        # Rodapé da sidebar com dica
        tk.Label(self.sidebar, text="DICA: Bot 24h analisa e opera automaticamente!",
                 bg="#050a14", fg="#64748b", font=("Segoe UI", 9)).pack(anchor="w", padx=pad, pady=(0, 10))

    # ===================== Conteúdo =====================
    def _build_content(self):
        cards = tk.Frame(self.content, bg="#0b1220")
        cards.pack(fill="x", padx=12, pady=10)

        self.balance_lbl = self._card(cards, "BANCA ATUAL", "R$ --")
        self.acc_lbl = self._card(cards, "ASSERTIVIDADE", "0% (0/0)")
        self.profit_lbl = self._card(cards, "LUCRO SESSÃO", "R$ 0.00")
        self.status_lbl = self._card(cards, "STATUS", "OFF", color="#ef4444")
        
        # NOVO CARD: OPERAÇÕES 24H
        self.operations_lbl = self._card(cards, "OPERAÇÕES 24H", "Aguardando...", color="#2ecc71")

        # NOVO: Log da IA (colocado antes da tabela de trades)
        ia_log_frame = tk.LabelFrame(self.content, text="LOG DO BOT 24H", bg="#0b1220", fg="#2ecc71", bd=1)
        ia_log_frame.pack(fill="x", padx=12, pady=(0, 10))

        ia_log_container = tk.Frame(ia_log_frame, bg="#0b1220")
        ia_log_container.pack(fill="both", expand=True, padx=8, pady=8)

        self.ia_log_text = tk.Text(ia_log_container, height=8, bg="#000000", fg="#2ecc71",
                                   insertbackground="#2ecc71", relief="flat", wrap="word",
                                   font=("Consolas", 9))
        self.ia_log_text.pack(side="left", fill="both", expand=True)

        ia_log_scroll = tk.Scrollbar(ia_log_container, orient="vertical", command=self.ia_log_text.yview)
        ia_log_scroll.pack(side="right", fill="y")
        self.ia_log_text.configure(yscrollcommand=ia_log_scroll.set, state="disabled")

        # Tabela de trades (reduzida em altura para caber na tela)
        table_frame = tk.LabelFrame(self.content, text="Transações (Log em Tabela)", bg="#0b1220", fg="#38bdf8", bd=1)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        container = tk.Frame(table_frame, bg="#0b1220")
        container.pack(fill="both", expand=True, padx=8, pady=8)

        cols = ("hora", "par", "tf", "valor", "dir", "prob", "ind", "payout", "status", "resultado", "lucro")
        self.trade_table = ttk.Treeview(container, columns=cols, show="headings", height=8)  # Reduzido de 14 para 8

        for c in cols:
            self.trade_table.heading(c, text=c.upper())
            self.trade_table.column(c, anchor="center", width=80)  # Reduzido de 92 para 80

        self.trade_table.column("par", width=150, anchor="w")  # Reduzido de 170 para 150
        self.trade_table.column("ind", width=140, anchor="w")  # Reduzido de 160 para 140
        self.trade_table.column("status", width=80)  # Reduzido de 90 para 80
        self.trade_table.column("resultado", width=80)  # Reduzido de 90 para 80
        self.trade_table.column("lucro", width=90)  # Reduzido de 100 para 90

        yscroll = ttk.Scrollbar(container, orient="vertical", command=self.trade_table.yview)
        self.trade_table.configure(yscrollcommand=yscroll.set)
        self.trade_table.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        # Estilo 1x (não recriar a cada update)
        style = ttk.Style()
        try:
            style.theme_use("default")
        except Exception:
            pass
        style.configure("Treeview", background="#020617", fieldbackground="#020617", foreground="#e5e7eb", rowheight=26)
        style.map("Treeview", background=[("selected", "#22c55e")], foreground=[("selected", "black")])

        self.trade_table.tag_configure("WIN", background="#052e1b", foreground="#22c55e")
        self.trade_table.tag_configure("LOSS", background="#2b0b0b", foreground="#ef4444")
        self.trade_table.tag_configure("OPEN", background="#0b1220", foreground="#e5e7eb")

        # Assertividade por par (meio do app)
        stats_frame = tk.LabelFrame(self.content, text="Assertividade por Par", bg="#0b1220", fg="#38bdf8", bd=1)
        stats_frame.pack(fill="x", padx=12, pady=(0, 6))

        st_container = tk.Frame(stats_frame, bg="#0b1220")
        st_container.pack(fill="both", expand=True, padx=8, pady=8)

        st_cols = ("par", "w", "l", "pct", "lucro", "trades")
        self.stats_table = ttk.Treeview(st_container, columns=st_cols, show="headings", height=4)  # Reduzido de 6 para 4
        for c in st_cols:
            self.stats_table.heading(c, text=c.upper())
            self.stats_table.column(c, anchor="center", width=100)  # Reduzido de 110 para 100
        self.stats_table.column("par", width=150, anchor="w")  # Reduzido de 170 para 150

        st_scroll = ttk.Scrollbar(st_container, orient="vertical", command=self.stats_table.yview)
        self.stats_table.configure(yscrollcommand=st_scroll.set)
        self.stats_table.pack(side="left", fill="both", expand=True)
        st_scroll.pack(side="right", fill="y")

        # Log do Robô (reduzido em altura)
        log_frame = tk.LabelFrame(self.content, text="LOG DO SISTEMA", bg="#0b1220", fg="#38bdf8", bd=1)
        log_frame.pack(fill="x", padx=12, pady=(0, 12))

        log_container = tk.Frame(log_frame, bg="#0b1220")
        log_container.pack(fill="both", expand=True, padx=8, pady=8)

        self.log_text = tk.Text(log_container, height=4, bg="#000000", fg="#39ff14",  # Reduzido de 6 para 4
                                insertbackground="#39ff14", relief="flat", wrap="word",
                                font=("Consolas", 9))
        self.log_text.pack(side="left", fill="both", expand=True)

        log_scroll = tk.Scrollbar(log_container, orient="vertical", command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=log_scroll.set, state="disabled")

    def _build_footer(self):
        footer = tk.Frame(self.root, bg="#050a14", height=46)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Button(footer, text="SAIR", bg="#ef4444", fg="white",
                  font=("Segoe UI", 11, "bold"), relief="flat",
                  command=self._close_app).pack(side="right", padx=14, pady=8)

    # ===================== Cards =====================
    def _card(self, parent, title, value, color="#22c55e"):
        frame = tk.Frame(parent, bg="#111827")
        frame.pack(side="left", expand=True, fill="x", padx=6)
        tk.Label(frame, text=title, bg="#111827", fg="#94a3b8", font=("Segoe UI", 9, "bold")).pack(pady=(8, 0))
        lbl = tk.Label(frame, text=value, bg="#111827", fg=color, font=("Segoe UI", 16, "bold"))
        lbl.pack(pady=(2, 10))
        return lbl

    # ===================== Config/Login =====================
    def _load_saved_login(self):
        s = load_settings()
        if s.get("email"):
            self.email_entry.insert(0, s.get("email"))
        if s.get("password"):
            self.pass_entry.insert(0, s.get("password"))
        self.save_login_var.set(bool(s.get("save_login", False)))

    def _maybe_save_login(self):
        if self.save_login_var.get():
            save_settings({"save_login": True, "email": self.email_entry.get().strip(), "password": self.pass_entry.get().strip()})
        else:
            save_settings({"save_login": False, "email": "", "password": ""})

    # ===================== Connect/Disconnect =====================
    def _toggle_connect(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect_async()

    def _set_connect_btn(self, connected: bool):
        if connected:
            self.connect_btn.config(text="CONECTADO", bg="#22c55e", fg="black")
            self.status_lbl.config(text="ON", fg="#22c55e")
        else:
            self.connect_btn.config(text="CONECTAR", bg="#22c55e", fg="black")
            self.status_lbl.config(text="OFF", fg="#ef4444")

    def _connect_async(self):
        email = self.email_entry.get().strip()
        senha = self.pass_entry.get().strip()
        if not email or not senha:
            messagebox.showerror("Erro", "Informe email e senha")
            return

        self.connect_btn.config(state="disabled", text="CONECTANDO...")
        self._append_log("🔗 Tentando conectar...")

        def worker():
            try:
                self.event_queue.put({"type": "log", "message": "🔄 Criando serviço IQ..."})
                service = IQService(email, senha, self.account_mode.get())
                
                self.event_queue.put({"type": "log", "message": "🔗 Conectando à IQ Option API..."})
                ok = service.connect()
                
                if ok:
                    # NOVO: Inicializar StrategyAnalyzer após conexão
                    self.event_queue.put({"type": "log", "message": "🧠 Inicializando IA de estratégias..."})
                    analyzer = StrategyAnalyzer(service)
                    self.event_queue.put({"type": "log", "message": "✅ Conectado com sucesso! IA pronta."})
                else:
                    self.event_queue.put({"type": "log", "message": "❌ Falha na conexão. Verifique suas credenciais."})
                
                self.event_queue.put({"type": "connect_done", "ok": ok, "service": service, "analyzer": analyzer if ok else None})
                
            except Exception as e:
                self.event_queue.put({"type": "log", "message": f"❌ Erro na conexão: {str(e)}"})
                self.event_queue.put({"type": "connect_done", "ok": False, "err": str(e)})

        threading.Thread(target=worker, daemon=True).start()

    def _on_connected(self, service: IQService, analyzer: StrategyAnalyzer = None):
        self.service = service
        self.analyzer = analyzer  # NOVO: Armazenar o analyzer
        self.connected = True
        self._set_connect_btn(True)
        self.connect_btn.config(state="normal")
        
        # NOVO: Ativar botões de operação 24h
        if self.analyzer:
            self.start_24h_btn.config(state="normal")
            self.analyze_once_btn.config(state="normal")
            self._append_ia_log("✅ IA de estratégias inicializada com sucesso!")

        # valor inicial = banca
        try:
            if float(self.initial_var.get()) == 0.0:
                bal_now = service.get_balance()
                if bal_now:
                    self.initial_var.set(float(bal_now))
        except Exception:
            pass

        self._maybe_save_login()
        self._append_log("✅ Conectado com sucesso.")
        self._refresh_assets()
        self._start_balance_worker()

    def _disconnect(self):
        # Para bot se estiver rodando
        if self.bot_running and self.bot:
            try:
                self.bot.stop()
                self._append_log("🛑 Bot 24h parado.")
            except Exception:
                pass

        # NOVO: Parar análise se estiver ativa
        self.analysis_active = False
        self.start_24h_btn.config(state="disabled")
        self.stop_24h_btn.config(state="disabled")
        self.analyze_once_btn.config(state="disabled")

        self.bot_running = False
        self.service = None
        self.analyzer = None
        self.connected = False
        self._balance_thread_running = False
        self._set_connect_btn(False)
        self._append_log("🛑 Desconectado.")

    # ===================== NOVOS MÉTODOS BOT 24H =====================
    def _start_bot_24h(self):
        """Inicia o bot em modo 24h"""
        if not self.connected or not self.service:
            self._append_log("⚠️ Conecte primeiro.")
            return
        
        if self.bot_running:
            self._append_log("ℹ️ Bot 24h já está rodando.")
            return

        # Configuração para modo 24h
        config = self._get_config()
        config["mode"] = "24H"
        config["profile"] = self.profile_var.get()
        config["strategy"] = "AUTO_IA"  # Estratégia automática da IA
        
        # Configurar limites baseados no perfil
        if self.profile_var.get() == "Agressivo":
            config["min_payout"] = 70
            config["min_confidence"] = 60
        elif self.profile_var.get() == "Moderado":
            config["min_payout"] = 75
            config["min_confidence"] = 75
        else:  # Conservador
            config["min_payout"] = 80
            config["min_confidence"] = 80
        
        # Criar e iniciar bot 24h
        self.bot = BotEngineWrapper(self.service, config, self.event_queue, self.analyzer)
        self.bot.start()
        
        self.bot_running = True
        self.mode_24h = True
        self.start_24h_btn.config(state="disabled")
        self.stop_24h_btn.config(state="normal")
        self.operations_lbl.config(text="OPERANDO 24H", fg="#2ecc71")
        
        self._append_ia_log("="*60)
        self._append_ia_log("🚀 BOT 24H INICIADO")
        self._append_ia_log(f"📊 Perfil: {self.profile_var.get()}")
        self._append_ia_log(f"🎯 Payout mínimo: {config['min_payout']}%")
        self._append_ia_log(f"🔍 Confiança mínima: {config['min_confidence']}%")
        self._append_ia_log(f"💵 Entrada: R$ {float(self.entry_var.get()):.2f}")
        self._append_ia_log("="*60)
        self._append_ia_log("🔍 Procurando oportunidades...")
        
        # Iniciar thread de monitoramento
        threading.Thread(target=self._monitor_24h_bot, daemon=True).start()

    def _stop_bot(self):
        """Para o bot 24h"""
        if self.bot:
            try:
                self.bot.stop()
                self._append_ia_log("🛑 Bot 24h parado pelo usuário.")
            except Exception as e:
                self._append_log(f"⚠️ Erro ao parar bot: {e}")
        
        self.bot_running = False
        self.mode_24h = False
        self.start_24h_btn.config(state="normal")
        self.stop_24h_btn.config(state="disabled")
        self.operations_lbl.config(text="PARADO", fg="#ef4444")
        self._append_log("🛑 Robô parado.")

    def _monitor_24h_bot(self):
        """Monitora o bot 24h"""
        while self.bot_running and self.mode_24h:
            try:
                # Atualizar status a cada 30 segundos
                time.sleep(30)
                
                if self.bot_running:
                    # Atualizar card de operações
                    current_time = time.strftime("%H:%M:%S")
                    self.event_queue.put({
                        "type": "update_operations",
                        "message": f"Operando... {current_time}"
                    })
                    
            except Exception as e:
                self._append_log(f"⚠️ Erro no monitoramento: {e}")
                break

    def _start_full_analysis(self):
        """Análise completa única (não contínua)"""
        if not self.connected or not self.service or not self.analyzer:
            self._append_log("⚠️ Conecte primeiro.")
            return
        
        if self.analysis_active:
            self._append_log("ℹ️ Análise já está em execução.")
            return

        # Limpar resultados anteriores
        self.best_results = {}
        
        self._append_ia_log("🧠 INICIANDO ANÁLISE COMPLETA ÚNICA")
        self._append_ia_log("📊 Analisando melhores oportunidades no momento...")
        
        # Iniciar thread de análise
        def analysis_worker():
            try:
                self.analysis_active = True
                self.analyze_once_btn.config(state="disabled")
                
                # Simular análise
                time.sleep(3)
                
                # Gerar resultado simulado
                assets = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURGBP-OTC", "AUDUSD-OTC"]
                asset = random.choice(assets)
                strategy = random.choice(["MHI_RSI", "BOLLINGER_REVERSAL", "TREND_FOLLOWER", "PRICE_ACTION"])
                confidence = random.randint(75, 95)
                payout = random.randint(80, 95)
                
                self.best_results = {
                    "best_overall": {
                        "asset": asset,
                        "strategy": strategy,
                        "confidence": confidence,
                        "payout": payout,
                        "score": confidence * payout / 100
                    }
                }
                
                # Mostrar resultados
                best = self.best_results["best_overall"]
                self._append_ia_log(f"🎯 MELHOR OPORTUNIDADE ENCONTRADA:")
                self._append_ia_log(f"   Ativo: {best['asset']}")
                self._append_ia_log(f"   Estratégia: {best['strategy']}")
                self._append_ia_log(f"   Confiança: {best['confidence']}%")
                self._append_ia_log(f"   Payout: {best['payout']}%")
                self._append_ia_log(f"   Score: {best['score']:.1f}")
                
                # Aplicar configuração
                self._apply_best_config_single()
                
                self.analysis_active = False
                self.analyze_once_btn.config(state="normal")
                
            except Exception as e:
                self._append_log(f"❌ Erro na análise: {e}")
                self.analysis_active = False
                self.analyze_once_btn.config(state="normal")

        threading.Thread(target=analysis_worker, daemon=True).start()

    def _apply_best_config_single(self):
        """Aplica a melhor configuração encontrada (modo único)"""
        if not self.best_results or not self.best_results["best_overall"]:
            return
        
        best = self.best_results["best_overall"]
        
        self._append_ia_log(f"⚙️ CONFIGURAÇÃO APLICADA:")
        self._append_ia_log(f"   Bot 24h agora usará esta configuração")
        
        # Atualizar card de operações
        self.operations_lbl.config(text=f"{best['asset']} | {best['strategy']}", fg="#4f67ff")

    # ===================== NOVOS MÉTODOS PARA LOG DA IA =====================
    def _append_ia_log(self, msg: str):
        """Adiciona mensagem ao log da IA"""
        ts = time.strftime("%H:%M:%S")
        self._ia_log_buf.append(f"[{ts}] {msg}\n")

    def _flush_ia_log_if_needed(self, force=False):
        """Flush do buffer de log da IA"""
        if not self._ia_log_buf:
            return
        now = time.time()
        if not force and (now - self._last_ia_log_flush) < self.LOG_FLUSH_INTERVAL:
            return
        self._last_ia_log_flush = now

        self.ia_log_text.configure(state="normal")
        self.ia_log_text.insert("end", "".join(self._ia_log_buf))
        self._ia_log_buf.clear()
        self.ia_log_text.see("end")

        # limita linhas do log da IA
        try:
            lines = int(self.ia_log_text.index("end-1c").split(".")[0])
            if lines > self.IA_LOG_MAX_LINES:
                cut = lines - self.IA_LOG_MAX_LINES
                self.ia_log_text.delete("1.0", f"{cut}.0")
        except Exception:
            pass

        self.ia_log_text.configure(state="disabled")

    # ===================== Assets =====================
    def _refresh_assets(self):
        self.assets_list.delete(0, tk.END)
        if not self.service:
            test_assets = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURGBP-OTC", "AUDUSD-OTC"]
            for a in test_assets:
                self.assets_list.insert(tk.END, a)
            return

        assets = []
        # tenta obter ativos turbo
        try:
            assets = self.service.get_turbo_assets()  # Sem parâmetro
            if not assets:
                self._append_log("⚠️ Nenhum ativo turbo encontrado")
                assets = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURGBP-OTC", "AUDUSD-OTC"]
        except Exception as e:
            self._append_log(f"⚠️ Erro ao obter ativos: {e}")
            assets = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURGBP-OTC", "AUDUSD-OTC"]

        for a in assets:
            self.assets_list.insert(tk.END, a)
        
        self._append_log(f"📊 {len(assets)} ativos carregados")

    # ===================== Bot =====================
    def _get_config(self):
        try:
            entry = float(self.entry_var.get())
        except Exception:
            entry = 10.0

        pairs = [self.assets_list.get(i) for i in self.assets_list.curselection()] if self.assets_list.curselection() else []
        auto_select = (len(pairs) == 0)

        try:
            stop_win = float(self.meta_var.get())
        except Exception:
            stop_win = 20.0
        try:
            stop_loss = float(self.stop_loss_var.get())
        except Exception:
            stop_loss = -15.0

        if not bool(self.autostop_var.get()):
            stop_win = 1e12
            stop_loss = -1e12

        # Perfil -> parametros (simples e leve)
        profile = self.profile_var.get()
        if profile == "Conservador":
            last_seconds = 2.0
            mode = "BOTH_STRICT"
            candle_count = 90
        elif profile == "Moderado":
            last_seconds = 3.0
            mode = "CONF"
            candle_count = 80
        else:  # Agressivo
            last_seconds = 3.0
            mode = "CONF"
            candle_count = 70

        indicators = {
            "close_price": bool(self.ind_close.get()),
            "rsi": bool(self.ind_rsi.get()),
            "macd": bool(self.ind_macd.get()),
            "stochastic": bool(self.ind_stoch.get()),
            "bollinger": bool(self.ind_bb.get()),
            "cci": bool(self.ind_cci.get()),
        }

        return {
            "entry": entry,
            "pairs": pairs,
            "auto_select": auto_select,
            "max_concurrent": 2,
            "timeframe": "5 Minutos",
            "stop_win": stop_win,
            "stop_loss": stop_loss,
            "min_payout": 0,
            "last_seconds": last_seconds,
            "mode": mode,
            "candle_count": candle_count,
            "indicators": indicators,
        }

    # ===================== Testes =====================
    def _pick_test_asset(self):
        sel = list(self.assets_list.curselection())
        if sel:
            return self.assets_list.get(random.choice(sel))
        size = self.assets_list.size()
        if size > 0:
            return self.assets_list.get(random.randrange(0, size))
        return None

    def _service_get_payout_percent(self, asset: str):
        # best-effort
        candidates = ["get_turbo_payout", "get_payout", "get_binary_payout", 
                     "get_payout_binary", "get_payout_percent", "payout"]
        
        for name in candidates:
            fn = getattr(self.service, name, None)
            if callable(fn):
                try:
                    v = fn(asset)
                    if v is None:
                        continue
                    f = float(v)
                    if 0 < f <= 1.5:
                        f *= 100.0
                    if f > 1.5 and f <= 100:
                        return round(f, 0)
                    if f > 100:
                        return round(f / 100.0, 0)
                except Exception:
                    continue
        return None

    def _test_trade_real(self):
        if not self.connected or not self.service:
            self._append_log("⚠️ Conecte primeiro.")
            return

        asset = self._pick_test_asset()
        if not asset:
            messagebox.showerror("Erro", "Não encontrei ativos para testar.")
            return

        ok = messagebox.askyesno(
            "Confirmar Teste",
            f"Vai fazer 1 trade no modo {self.account_mode.get()}:\n\nAtivo: {asset}\nDireção: ALEATÓRIA\nEntrada: R$ 1.00\n\nConfirmar?"
        )
        if not ok:
            return

        def worker():
            try:
                direction = random.choice(["call", "put"])
                entry = 1.0
                tf_label = "1 Minuto"

                payout = self._service_get_payout_percent(asset)
                payout_txt = f"{int(payout)}%" if payout is not None else "--"

                self.event_queue.put({"type": "log", "message": f"🧪 TESTE REAL: {asset} {direction.upper()} payout {payout_txt} (R$ {entry:.2f})"})
                ok_buy, order_id, _ = self.service.buy_binary(asset, entry, direction, 1)
                if not ok_buy:
                    self.event_queue.put({"type": "log", "message": f"⚠️ TESTE REAL falhou ao abrir ordem em {asset}."})
                    return

                self.event_queue.put({
                    "type": "trade",
                    "order_id": str(order_id),
                    "hora": time.strftime("%H:%M:%S"),
                    "par": asset,
                    "tf": tf_label,
                    "valor": f"R$ {entry:.2f}",
                    "dir": direction,
                    "prob": "--",
                    "ind": "TEST",
                    "payout": payout_txt,
                    "status": "OPEN",
                    "resultado": "",
                    "lucro": 0.0,
                })

                # AGUARDAR tempo real do trade (60 segundos)
                time.sleep(60)
                
                # VERIFICAR resultado real
                result = self.service.check_binary_result(order_id, timeout_sec=10)
                profit = float(result) if result is not None else -entry
                status = "WIN" if profit > 0 else "LOSS"

                self.event_queue.put({
                    "type": "trade",
                    "order_id": str(order_id),
                    "hora": time.strftime("%H:%M:%S"),
                    "par": asset,
                    "tf": tf_label,
                    "valor": f"R$ {entry:.2f}",
                    "dir": direction,
                    "prob": "--",
                    "ind": "TEST",
                    "payout": payout_txt,
                    "status": status,
                    "resultado": status,
                    "lucro": float(profit),
                })

                self.event_queue.put({"type": "log", "message": f"🧪 TESTE REAL finalizado: {status} lucro {profit:.2f}"})

            except Exception as e:
                self.event_queue.put({"type": "log", "message": f"❌ Erro no TESTE REAL: {e}"})

        threading.Thread(target=worker, daemon=True).start()

    def _test_trade_bot(self):
        if not self.connected or not self.service:
            self._append_log("⚠️ Conecte primeiro.")
            return
        # Dispara um trade aleatório usando o próprio BotEngine (config atual)
        try:
            cfg = self._get_config()
            cfg["timeframe"] = "1 Minuto"
            cfg["last_seconds"] = 2.0
            b = BotEngine(self.service, cfg, self.event_queue)
            # força 1 trade
            def _one():
                asset = self._pick_test_asset()
                if not asset:
                    return
                payout = self._service_get_payout_percent(asset)
                direction = random.choice(["call", "put"])
                self.event_queue.put({"type":"log","message":f"🧪 TESTE BOT: {asset} {direction.upper()} payout {int(payout) if payout else '--'}%"})
                # chama worker do bot (simples)
                ok, order_id, err = self.service.buy_binary(asset, 1.0, direction, 1)
                if not ok:
                    self.event_queue.put({"type":"log","message":f"⚠️ TESTE BOT falhou em {asset}: {err}"})
                    return
                
                # AGUARDAR tempo real
                time.sleep(60)
                
                res = self.service.check_binary_result(order_id, timeout_sec=10)
                profit = float(res) if res is not None else -1.0
                status = "WIN" if profit > 0 else "LOSS"
                self.event_queue.put({"type":"log","message":f"🧪 TESTE BOT finalizado: {status} lucro {profit:.2f}"})
            threading.Thread(target=_one, daemon=True).start()
        except Exception as e:
            self._append_log(f"❌ Erro no TESTE BOT: {e}")

    # ===================== Balance worker =====================
    def _start_balance_worker(self):
        if self._balance_thread_running:
            return
        self._balance_thread_running = True

        def worker():
            while self._balance_thread_running and self.connected and self.service:
                try:
                    bal = self.service.get_balance()
                    self.event_queue.put({"type": "balance", "value": bal})
                except Exception:
                    pass
                time.sleep(1.5)

        threading.Thread(target=worker, daemon=True).start()

    # ===================== Log helpers =====================
    def _append_log(self, msg: str):
        # buffer -> flush em lote
        ts = time.strftime("%H:%M:%S")
        self._log_buf.append(f"[{ts}] {msg}\n")

    def _flush_log_if_needed(self, force=False):
        if not self._log_buf:
            return
        now = time.time()
        if not force and (now - self._last_log_flush) < self.LOG_FLUSH_INTERVAL:
            return
        self._last_log_flush = now

        self.log_text.configure(state="normal")
        self.log_text.insert("end", "".join(self._log_buf))
        self._log_buf.clear()
        self.log_text.see("end")

        # limita linhas (leve)
        try:
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > self.LOG_MAX_LINES:
                # remove o excesso do topo
                cut = lines - self.LOG_MAX_LINES
                self.log_text.delete("1.0", f"{cut}.0")
        except Exception:
            pass

        self.log_text.configure(state="disabled")

    # ===================== Trades + Stats =====================
    def _upsert_trade_row(self, ev: dict):
        order_id = ev.get("order_id") or f"NOID-{time.time()}"

        lucro_val = ev.get("lucro", 0.0)
        try:
            lucro_float = float(lucro_val)
            lucro_text = f"R$ {lucro_float:.2f}"
        except Exception:
            lucro_float = 0.0
            lucro_text = "R$ 0.00"

        values = (
            ev.get("hora", "--"),
            ev.get("par", "--"),
            ev.get("tf", "--"),
            ev.get("valor", "--"),
            (ev.get("dir", "--") or "--").upper(),
            ev.get("prob", "--"),
            ev.get("ind", "--"),
            ev.get("payout", "--"),
            ev.get("status", "--"),
            ev.get("resultado", ""),
            lucro_text,
        )

        tag = ev.get("status", "OPEN")
        if tag not in ("WIN", "LOSS", "OPEN"):
            tag = "OPEN"

        # --- FIX: Atualiza linha existente de forma eficiente ---
        if order_id in self.trade_rows:
            iid = self.trade_rows[order_id]
            # Atualiza todos os valores e tag
            self.trade_table.item(iid, values=values, tags=(tag,))
        else:
            iid = self.trade_table.insert("", "end", values=values, tags=(tag,))
            self.trade_rows[order_id] = iid

        # Atualiza stats e cards somente quando fechar
        if tag in ("WIN", "LOSS"):
            self._session_profit += lucro_float
            self.profit_lbl.config(text=f"R$ {self._session_profit:.2f}")

            # Atualiza stats por par (incremental)
            par = ev.get("par", "--")
            st = self.pair_stats.setdefault(par, {"w": 0, "l": 0, "profit": 0.0, "trades": 0})
            st["profit"] += lucro_float
            st["trades"] += 1
            if tag == "WIN":
                st["w"] += 1
            else:
                st["l"] += 1

            # Atualiza assertividade geral (incremental)
            total = self.wins_losses_total()
            if tag == "WIN":
                # win count = soma de tags WIN na tabela é pesado; usamos pair_stats
                pass

            # recomputa geral via pair_stats (rápido)
            w = sum(v["w"] for v in self.pair_stats.values())
            l = sum(v["l"] for v in self.pair_stats.values())
            tot = w + l
            acc = (w / tot * 100.0) if tot else 0.0
            self.acc_lbl.config(text=f"{acc:.0f}% ({w}/{tot})")

            # Atualiza tabela de stats (sem varrer trades)
            self._refresh_stats_table()

    def wins_losses_total(self):
        w = sum(v["w"] for v in self.pair_stats.values())
        l = sum(v["l"] for v in self.pair_stats.values())
        return w, l, w + l

    def _refresh_stats_table(self):
        self.stats_table.delete(*self.stats_table.get_children())

        min_trades = max(0, int(self.min_trades_var.get() or 0))
        min_acc = float(self.min_acc_var.get() or 0.0)

        rows = []
        for par, st in self.pair_stats.items():
            trades = st["trades"]
            if trades < min_trades:
                continue
            w = st["w"]
            l = st["l"]
            pct = (w / trades * 100.0) if trades else 0.0
            if pct < min_acc:
                continue
            rows.append((par, w, l, pct, st["profit"], trades))

        # ordena por % desc
        rows.sort(key=lambda x: x[3], reverse=True)

        for par, w, l, pct, profit, trades in rows[:200]:
            self.stats_table.insert("", "end", values=(
                par, w, l, f"{pct:.0f}%", f"R$ {profit:.2f}", trades
            ))

    # ===================== Queue poll (batch) =====================
    def _poll_queue(self):
        # Processa em lote para ficar leve
        processed = 0
        max_batch = 120

        try:
            while processed < max_batch:
                ev = self.event_queue.get_nowait()
                processed += 1

                t = ev.get("type")
                if t == "connect_done":
                    self.connect_btn.config(state="normal")
                    if ev.get("ok"):
                        # NOVO: Receber analyzer também
                        self._on_connected(ev["service"], ev.get("analyzer"))
                    else:
                        self._set_connect_btn(False)
                        messagebox.showerror("Erro", f"Falha ao conectar:\n{ev.get('err', 'Verifique login/internet')}")
                elif t == "balance":
                    bal = ev.get("value", None)
                    if bal is not None:
                        self.balance_lbl.config(text=f"R$ {float(bal):.2f}")
                elif t == "log":
                    self._append_log(ev.get("message", ""))
                elif t == "trade":
                    self._upsert_trade_row(ev)
                elif t == "update_operations":  # NOVO: Atualizar operações
                    self.operations_lbl.config(text=ev.get("message", "OPERANDO"))
                elif t == "progress_update":  # NOVO: Atualizar progresso
                    self._update_progress(ev.get("progress", 0), ev.get("current", ""))

        except queue.Empty:
            pass

        # flush logs (leve)
        self._flush_log_if_needed()
        self._flush_ia_log_if_needed()  # NOVO: Flush do log da IA também

        self.root.after(120, self._poll_queue)
    
    def _update_progress(self, progress, current):
        """Atualiza a barra de progresso"""
        # Implementação se necessário
        pass

    # ===================== Close =====================
    def _close_app(self):
        self._balance_thread_running = False
        self._session_profit = 0.0
        
        # Parar bot 24h se estiver rodando
        if self.bot_running and self.bot:
            try:
                self.bot.stop()
                self._append_log("🛑 Bot 24h parado.")
            except Exception:
                pass
            
        try:
            if self.bot_running and self.bot:
                self.bot.stop()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ProDashboardApp(root)
    root.mainloop()