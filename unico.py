# -*- coding: utf-8 -*-
import FreeSimpleGUI as sg
import time
import threading
import random
import logging
import sys
from iqoptionapi.stable_api import IQ_Option
from collections import defaultdict
from datetime import datetime
import pandas as pd
import math
from typing import Optional, Dict, List
import queue

# Configurar encoding para Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Silenciar logs técnicos
logging.getLogger("iqoptionapi").setLevel(logging.CRITICAL)
logging.getLogger("websocket").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)


# =========================================
# TEMA PROFISSIONAL - DASHBOARD DARK
# =========================================
PROFESSIONAL_THEME = {
    'BACKGROUND': '#0E1218',      # Fundo principal mais sóbrio
    'PANEL': '#1A1F2A',            # Painéis em tom mais claro
    'ACCENT': '#2962FF',            # Azul profissional
    'ACCENT2': '#00C853',           # Verde para ganhos
    'TEXT': '#E8EAF2',              # Texto principal
    'MUTE': '#8C9AA8',              # Texto secundário
    'SUCCESS': '#00C853',           # Verde sucesso
    'WARN': '#FFB300',               # Amarelo aviso
    'ERROR': '#D32F2F',              # Vermelho erro
    'INFO': '#2979FF',               # Azul informação
    'BORDER': '#2F3747',             # Borda dos painéis
    'CONSOLE_BG': '#0A0D12',         # Fundo do terminal (preto)
    'CONSOLE_TEXT': '#B2F0B2',       # Texto verde terminal
    'CONSOLE_ERROR': '#FF8A80',       # Vermelho claro para erros
    'CONSOLE_SUCCESS': '#69F0AE',     # Verde claro para sucessos
    'CONSOLE_WARN': '#FFE57F',        # Amarelo para avisos
    'CONSOLE_INFO': '#82B1FF',        # Azul para info
    'BTN_PRIMARY': ('white', '#2962FF'),
    'BTN_SECONDARY': ('white', '#2F3747'),
    'BTN_DANGER': ('white', '#D32F2F'),
    'BTN_SUCCESS': ('white', '#00C853'),
    'INPUT_BG': '#0F141C',
}

# =========================================
# CLASSE DE LOG EM TEMPO REAL
# =========================================
class RealTimeLogger:
    """Sistema de logging em tempo real com fila para thread safety"""
    
    def __init__(self, callback):
        self.callback = callback
        self.queue = queue.Queue()
        self.running = True
        self.thread = threading.Thread(target=self._process_queue, daemon=True)
        self.thread.start()
    
    def _process_queue(self):
        while self.running:
            try:
                msg, level = self.queue.get(timeout=0.1)
                if self.callback:
                    self.callback(msg, level)
            except queue.Empty:
                continue
            except Exception:
                break
    
    def log(self, msg: str, level: str = 'info'):
        """Adiciona log à fila"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Formatar conforme o nível
        if level == 'error':
            formatted = f"❌ [{timestamp}] {msg}"
        elif level == 'success':
            formatted = f"✅ [{timestamp}] {msg}"
        elif level == 'win':
            formatted = f"💰 [{timestamp}] {msg}"
        elif level == 'loss':
            formatted = f"📉 [{timestamp}] {msg}"
        elif level == 'warn':
            formatted = f"⚠️ [{timestamp}] {msg}"
        elif level == 'signal':
            formatted = f"🚀 [{timestamp}] {msg}"
        elif level == 'pattern':
            formatted = f"🎯 [{timestamp}] {msg}"
        elif level == 'info':
            formatted = f"ℹ️ [{timestamp}] {msg}"
        else:
            formatted = f"[{timestamp}] {msg}"
        
        self.queue.put((formatted, level))
        
        # Também logar em arquivo
        logging.info(f"[{level.upper()}] {msg}")
    
    def stop(self):
        self.running = False


# =========================================
# GERENCIAMENTO DE BANCA SOROS/GALE
# =========================================
class SorosGale:
    def __init__(self, banca, stake_base, nivel_soros, nivel_gale, percent_soros=1.0, fator_gale=2.0):
        self.banca_atual = float(banca)
        self.stake_base = float(stake_base)
        self.max_soros = int(nivel_soros)
        self.max_gale = int(nivel_gale)
        self.percent_soros = float(percent_soros)
        self.fator_gale = float(fator_gale)

        self.nivel_atual_soros = 0
        self.nivel_atual_gale = 0
        self.ultimo_lucro = 0.0
        self.wins = 0
        self.losses = 0
        self.dojis = 0
        
        # Histórico para estatísticas
        self.historico_stakes = []
        self.sequencia_atual = 0

    def calcular_stake(self):
        if self.banca_atual < 1.0: 
            return 0

        # Lógica MARTINGALE
        if self.nivel_atual_gale > 0:
            if self.nivel_atual_gale > self.max_gale:
                self.nivel_atual_gale = 0
                return self.stake_base
            
            stake = self.stake_base * (self.fator_gale ** self.nivel_atual_gale)
            stake = round(min(stake, self.banca_atual * 0.1), 2)  # Máx 10% da banca
            self.historico_stakes.append(('gale', self.nivel_atual_gale, stake))
            return stake

        # Lógica SOROS 
        if self.nivel_atual_soros > 0:
            if self.nivel_atual_soros > self.max_soros:
                self.nivel_atual_soros = 0
                return self.stake_base
            
            lucro_reinvestido = self.ultimo_lucro * self.percent_soros
            stake = self.stake_base + lucro_reinvestido
            stake = round(min(stake, self.banca_atual * 0.1), 2)
            self.historico_stakes.append(('soros', self.nivel_atual_soros, stake))
            return stake

        # Mão Fixa
        self.historico_stakes.append(('fixa', 0, self.stake_base))
        return self.stake_base

    def atualizar_resultado(self, resultado, valor_real):
        self.banca_atual += valor_real

        if resultado == 'win':
            self.wins += 1
            self.ultimo_lucro = valor_real
            self.sequencia_atual = self.sequencia_atual + 1 if self.sequencia_atual > 0 else 1
            
            if self.nivel_atual_gale > 0:
                self.nivel_atual_gale = 0
                self.nivel_atual_soros = 1
            else:
                self.nivel_atual_soros += 1

        elif resultado == 'loss':
            self.losses += 1
            self.ultimo_lucro = 0
            self.sequencia_atual = self.sequencia_atual - 1 if self.sequencia_atual < 0 else -1
            
            self.nivel_atual_soros = 0
            self.nivel_atual_gale += 1
            
        elif resultado == 'doji':
            self.dojis += 1
            self.sequencia_atual = 0

    def obter_placar(self):
        return f"{self.wins}W - {self.losses}L - {self.dojis}D"
    
    def obter_info_entrada(self):
        if self.nivel_atual_gale > 0:
            return f"MARTINGALE {self.nivel_atual_gale}"
        elif self.nivel_atual_soros > 0:
            return f"SOROS {self.nivel_atual_soros}"
        else:
            return "FIXA"
    
    def get_stats(self):
        total = self.wins + self.losses + self.dojis
        win_rate = (self.wins / total * 100) if total > 0 else 0
        return {
            'total': total,
            'wins': self.wins,
            'losses': self.losses,
            'dojis': self.dojis,
            'win_rate': win_rate,
            'sequencia': self.sequencia_atual,
            'banca': self.banca_atual
        }


# =========================================
# ESTRATÉGIA DE CICLOS PROBABILÍSTICOS
# =========================================
class StrategyCiclos:
    def __init__(self, api, logger):
        self.api = api
        self.logger = logger
        self.nome = "Ciclos"
        self.last_found_patterns = {}

    def get_color(self, candle):
        if candle['close'] > candle['open']: 
            return 1  # Verde
        if candle['close'] < candle['open']: 
            return -1  # Vermelha
        return 0  # Doji

    def analisar(self, ativo, tf_segundos):
        try:
            candles = self.api.get_candles(ativo, tf_segundos, 120, time.time())
            if not candles or len(candles) < 20:
                return None, "Aguardando dados"
            
            df = pd.DataFrame(candles)
            asset_name = ativo
            
            last_found_pattern = self.last_found_patterns.get(asset_name)

            # Identificar padrão (AZUL ou ROSA)
            current_pattern = None
            lookback_limit = min(len(df) - 5, 100)
            
            for i in range(2, lookback_limit): 
                idx0, idx1, idx2, idx3 = -i, -i-1, -i-2, -i-3
                
                h0 = self.get_color(df.iloc[idx0])
                h1 = self.get_color(df.iloc[idx1])
                h2 = self.get_color(df.iloc[idx2])
                h3 = self.get_color(df.iloc[idx3])
                
                if h0 == 0 or h1 == 0 or h2 == 0 or h3 == 0: 
                    continue

                # AZUL
                if (h3 != h2) and (h2 == h1) and (h1 == h0):
                    current_pattern = 'AZUL'
                    break 
                
                # ROSA
                elif (h3 != h2) and (h2 == h1) and (h1 != h0) and (h0 == h3):
                    current_pattern = 'ROSA'
                    break 

            padrao_ativo = current_pattern
            
            if padrao_ativo and padrao_ativo != last_found_pattern:
                self.logger.log(f"{ativo} PADRÃO: {padrao_ativo}", 'pattern')
                self.last_found_patterns[asset_name] = padrao_ativo
            
            padrao_final = padrao_ativo if padrao_ativo else last_found_pattern
            
            if not padrao_final:
                return None, "⏳"

            # Gatilho de entrada
            c3 = self.get_color(df.iloc[-1]) 
            c2 = self.get_color(df.iloc[-2]) 
            c1 = self.get_color(df.iloc[-3]) 

            gatilho_pronto = (c1 != c2) and (c2 == c3) and c1 != 0 and c2 != 0

            if gatilho_pronto:
                if padrao_final == 'AZUL':
                    if c3 == -1:
                        return 'put', f"AZUL"
                    
                elif padrao_final == 'ROSA':
                    if c1 == 1:
                        return 'call', f"ROSA"
                    if c1 == -1:
                        return 'put', f"ROSA"

            return None, f"{padrao_final[:3]}"
            
        except Exception as e:
            return None, f"ERRO"


# =========================================
# ESTRATÉGIA FALSA ENTRADA
# =========================================
class StrategyFalsa:
    def __init__(self, api, logger):
        self.api = api
        self.logger = logger
        self.nome = "Falsa"
        self.historico_entradas = {}
        self.contador_reversao = {}
        self.ultima_entrada_timestamp = {}
        
    def analisar_tendencia(self, fechamentos, periodo=20):
        if len(fechamentos) < periodo:
            return 'neutro'
        media = sum(fechamentos[-periodo:]) / periodo
        if fechamentos[-1] > media:
            return 'alta'
        elif fechamentos[-1] < media:
            return 'baixa'
        return 'neutro'
    
    def analisar(self, ativo, tf_segundos):
        try:
            candles = self.api.get_candles(ativo, tf_segundos, 30, time.time())
            if not candles or len(candles) < 20:
                return None, "Dados"
            
            fechamentos = [c['close'] for c in candles]
            tendencia = self.analisar_tendencia(fechamentos)
            
            if ativo not in self.historico_entradas:
                self.historico_entradas[ativo] = []
                self.contador_reversao[ativo] = 0
                self.ultima_entrada_timestamp[ativo] = 0
            
            if time.time() - self.ultima_entrada_timestamp[ativo] < 45:
                return None, f"⏳"
            
            ultimas_velas = candles[-3:]
            verde_count = sum(1 for c in ultimas_velas if c['close'] > c['open'])
            vermelha_count = 3 - verde_count
            
            forca_momentum = abs(verde_count - vermelha_count)
            if forca_momentum < 2:
                return None, f"⚡{verde_count}-{vermelha_count}"
            
            if self.historico_entradas[ativo]:
                entradas_recentes = [e for e in self.historico_entradas[ativo] 
                                    if time.time() - e['timestamp'] < 600]
                
                if entradas_recentes:
                    ultima_entrada = entradas_recentes[-1]
                    
                    if ultima_entrada.get('resultado') == 'loss':
                        if time.time() - ultima_entrada['timestamp'] > 60:
                            if ultima_entrada['direcao'] == 'call' and vermelha_count >= 2:
                                self.contador_reversao[ativo] += 1
                                if self.contador_reversao[ativo] <= 2:
                                    return 'put', f"REV{self.contador_reversao[ativo]}"
                            elif ultima_entrada['direcao'] == 'put' and verde_count >= 2:
                                self.contador_reversao[ativo] += 1
                                if self.contador_reversao[ativo] <= 2:
                                    return 'call', f"REV{self.contador_reversao[ativo]}"
                    
                    elif ultima_entrada.get('resultado') == 'win':
                        self.contador_reversao[ativo] = 0
                        if ultima_entrada['direcao'] == 'call' and verde_count >= 2 and tendencia == 'alta':
                            return 'call', f"SEGUE"
                        elif ultima_entrada['direcao'] == 'put' and vermelha_count >= 2 and tendencia == 'baixa':
                            return 'put', f"SEGUE"
            
            if verde_count >= 2 and tendencia == 'alta' and forca_momentum >= 2:
                return 'call', f"DIRETA ↑"
            elif vermelha_count >= 2 and tendencia == 'baixa' and forca_momentum >= 2:
                return 'put', f"DIRETA ↓"
            
            return None, f"{tendencia[:3]}"
            
        except Exception:
            return None, "ERR"
    
    def registrar_resultado(self, ativo, direcao, resultado):
        if ativo not in self.historico_entradas:
            self.historico_entradas[ativo] = []
        
        self.historico_entradas[ativo].append({
            'direcao': direcao,
            'resultado': resultado,
            'timestamp': time.time()
        })
        self.ultima_entrada_timestamp[ativo] = time.time()
        
        if len(self.historico_entradas[ativo]) > 20:
            self.historico_entradas[ativo].pop(0)


# =========================================
# INTERFACE PRINCIPAL - DASHBOARD PROFISSIONAL
# =========================================
class ProBotDashboard:
    APP_TITLE = 'FRANCISX TRADING TERMINAL v8.0'
    WINDOW_TITLE = 'FrancisX Terminal - Professional Trading Dashboard'

    def __init__(self):
        self.palette = PROFESSIONAL_THEME
        
        self.api = None
        self.is_running = False
        self.logger = None
        self.gerenciamento = None
        
        # Dados de mercado
        self.mercado_info = {
            'conectado': False,
            'tipo_conta': 'DEMO',
            'saldo': 0,
            'lucro': 0,
            'win_rate': '0%',
            'ultima_atualizacao': '--:--:--'
        }
        
        # Fila de mensagens do terminal
        self.terminal_queue = queue.Queue()
        
        self.window = None
        self._build_layout()

    def _format_brl(self, value: float) -> str:
        return f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    def _terminal_callback(self, msg: str, level: str):
        """Callback para atualizar o terminal em tempo real"""
        self.terminal_queue.put((msg, level))

    def _update_terminal(self):
        """Atualiza o terminal com mensagens da fila"""
        try:
            while True:
                msg, level = self.terminal_queue.get_nowait()
                
                # Definir cor baseado no nível
                if level == 'error':
                    color = self.palette['CONSOLE_ERROR']
                elif level in ['success', 'win']:
                    color = self.palette['CONSOLE_SUCCESS']
                elif level == 'warn':
                    color = self.palette['CONSOLE_WARN']
                elif level in ['signal', 'pattern']:
                    color = self.palette['INFO']
                else:
                    color = self.palette['CONSOLE_TEXT']
                
                # Atualizar o elemento de terminal
                if self.window and '-TERMINAL-' in self.window.AllKeysDict:
                    current = self.window['-TERMINAL-'].get()
                    lines = current.split('\n')
                    if len(lines) > 100:  # Limitar a 100 linhas
                        lines = lines[-100:]
                    lines.append(msg)
                    self.window['-TERMINAL-'].update('\n'.join(lines))
                    
        except queue.Empty:
            pass

    def _build_layout(self):
        pal = self.palette
        
        # Layout superior - Header com status
        header = [
            [sg.Text(self.APP_TITLE, font=('Segoe UI Semibold', 18), text_color=pal['ACCENT'])],
            [sg.Text('Status:', font=('Segoe UI', 9), text_color=pal['MUTE']),
             sg.Text('DESCONECTADO', key='-STATUS-', font=('Segoe UI Semibold', 10), 
                    text_color=pal['ERROR'], size=(15, 1)),
             sg.Text('Conta:', font=('Segoe UI', 9), text_color=pal['MUTE']),
             sg.Text('DEMO', key='-TIPO_CONTA-', font=('Segoe UI Semibold', 10), 
                    text_color=pal['INFO'], size=(10, 1)),
             sg.Text('Atualização:', font=('Segoe UI', 9), text_color=pal['MUTE']),
             sg.Text('--:--:--', key='-ULT_ATUAL-', font=('Segoe UI', 9), text_color=pal['MUTE'])]
        ]

        # Painel de Controle Superior
        control_panel = [
            [sg.Button('🔌 CONECTAR', key='CONECTAR', button_color=pal['BTN_PRIMARY'], size=(12, 1)),
             sg.Button('🚀 INICIAR', key='-START-', disabled=True, button_color=pal['BTN_SUCCESS'], size=(12, 1)),
             sg.Button('🛑 PARAR', key='-STOP-', disabled=True, button_color=pal['BTN_DANGER'], size=(12, 1)),
             sg.Button('📊 STATUS', key='-STATUS_CONTA-', disabled=True, button_color=pal['BTN_SECONDARY'], size=(10, 1)),
             sg.Button('🧹 LIMPAR', key='-LIMPAR_TERMINAL-', button_color=pal['BTN_SECONDARY'], size=(10, 1)),
             sg.Button('⚙️ SAIR', key='SAIR', button_color=pal['BTN_DANGER'], size=(8, 1))]
        ]

        # Painel de Informações - DASHBOARD
        info_panel = [
            [sg.Frame('💵 SALDO', [
                [sg.Text('Inicial:', font=('Segoe UI', 9), text_color=pal['MUTE']),
                 sg.Text('R$ 0,00', key='-SALDO_INICIAL-', font=('Segoe UI Semibold', 14), 
                        text_color=pal['TEXT'], size=(14, 1), justification='right')],
                [sg.Text('Atual:', font=('Segoe UI', 9), text_color=pal['MUTE']),
                 sg.Text('R$ 0,00', key='-SALDO_ATUAL-', font=('Segoe UI Bold', 18), 
                        text_color=pal['ACCENT2'], size=(14, 1), justification='right')],
                [sg.Text('Lucro:', font=('Segoe UI', 9), text_color=pal['MUTE']),
                 sg.Text('R$ 0,00', key='-LUCRO-', font=('Segoe UI Bold', 16), 
                        text_color=pal['SUCCESS'], size=(14, 1), justification='right')],
            ], font=('Segoe UI Semibold', 10), border_width=1, relief=sg.RELIEF_SOLID, 
               background_color=pal['PANEL'], element_justification='right', size=(200, 130))],
            
            [sg.Frame('📊 PERFORMANCE', [
                [sg.Text('Placar:', font=('Segoe UI', 9), text_color=pal['MUTE']),
                 sg.Text('0W - 0L - 0D', key='-PLACAR-', font=('Segoe UI Semibold', 12), 
                        text_color=pal['SUCCESS'], size=(16, 1))],
                [sg.Text('Win Rate:', font=('Segoe UI', 9), text_color=pal['MUTE']),
                 sg.Text('0%', key='-WIN_RATE-', font=('Segoe UI Semibold', 12), 
                        text_color=pal['INFO'], size=(16, 1))],
                [sg.Text('Sequência:', font=('Segoe UI', 9), text_color=pal['MUTE']),
                 sg.Text('0', key='-SEQUENCIA-', font=('Segoe UI Semibold', 12), 
                        text_color=pal['WARN'], size=(16, 1))],
                [sg.Text('Total Trades:', font=('Segoe UI', 9), text_color=pal['MUTE']),
                 sg.Text('0', key='-TOTAL_TRADES-', font=('Segoe UI', 10), 
                        text_color=pal['TEXT'], size=(16, 1))],
            ], font=('Segoe UI Semibold', 10), border_width=1, relief=sg.RELIEF_SOLID, 
               background_color=pal['PANEL'], size=(200, 120))],
        ]

        # Painel de Configurações
        config_panel = [
            [sg.Frame('🔐 ACESSO', [
                [sg.Text('Email:', size=(7,1), text_color=pal['MUTE']), 
                 sg.Input(key='-EMAIL-', size=(28,1), background_color=pal['INPUT_BG'], 
                         text_color=pal['TEXT'], border_width=0)],
                [sg.Text('Senha:', size=(7,1), text_color=pal['MUTE']), 
                 sg.Input(key='-SENHA-', size=(28,1), password_char='*', 
                         background_color=pal['INPUT_BG'], text_color=pal['TEXT'], border_width=0)],
                [sg.Radio('DEMO', "R1", default=True, key='-PRACTICE-', text_color=pal['TEXT']), 
                 sg.Radio('REAL', "R1", key='-REAL-', text_color=pal['TEXT'])],
            ], font=('Segoe UI Semibold', 10), border_width=1, relief=sg.RELIEF_SOLID, 
               background_color=pal['PANEL'])],
            
            [sg.Frame('📈 ATIVO', [
                [sg.Text('Ativo:', size=(6,1), text_color=pal['MUTE']),
                 sg.Combo(['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'EURGBP', 'GBPJPY'], 
                          default_value='EURUSD', key='-ATIVO-', size=(12,1),
                          background_color=pal['INPUT_BG'], text_color=pal['TEXT']),
                 sg.Checkbox('OTC', key='-IS_OTC-', default=True, text_color=pal['TEXT'])],
                [sg.Text('Timeframe:', size=(8,1), text_color=pal['MUTE']),
                 sg.Combo(['M1 (1 min)', 'M5 (5 min)'], default_value='M1 (1 min)', 
                         key='-TF-', size=(15,1), background_color=pal['INPUT_BG'], 
                         text_color=pal['TEXT'])],
            ], font=('Segoe UI Semibold', 10), border_width=1, relief=sg.RELIEF_SOLID, 
               background_color=pal['PANEL'])],
            
            [sg.Frame('💰 ENTRADA', [
                [sg.Text('Valor R$:', size=(8,1), text_color=pal['MUTE']),
                 sg.Input(key='-VALOR-', size=(12,1), default_text='2.00', 
                         background_color=pal['INPUT_BG'], text_color=pal['TEXT'])],
                [sg.Text('Stop Win R$:', size=(8,1), text_color=pal['MUTE']),
                 sg.Input(key='-STOP_WIN-', size=(12,1), default_text='50.00', 
                         background_color=pal['INPUT_BG'], text_color=pal['TEXT'])],
                [sg.Text('Stop Loss R$:', size=(8,1), text_color=pal['MUTE']),
                 sg.Input(key='-STOP_LOSS-', size=(12,1), default_text='25.00', 
                         background_color=pal['INPUT_BG'], text_color=pal['TEXT'])],
            ], font=('Segoe UI Semibold', 10), border_width=1, relief=sg.RELIEF_SOLID, 
               background_color=pal['PANEL'])],
            
            [sg.Frame('🔄 GERENCIAMENTO', [
                [sg.Text('Max Soros:', size=(8,1), text_color=pal['MUTE']),
                 sg.Combo(['0', '1', '2', '3', '4', '5'], default_value='2', 
                         key='-MAX_SOROS-', size=(8,1), background_color=pal['INPUT_BG'])],
                [sg.Text('Max Gale:', size=(8,1), text_color=pal['MUTE']),
                 sg.Combo(['0', '1', '2', '3'], default_value='2', key='-MAX_GALE-', 
                         size=(8,1), background_color=pal['INPUT_BG'])],
                [sg.Text('Fator Gale:', size=(8,1), text_color=pal['MUTE']),
                 sg.Combo(['1.5', '2.0', '2.3', '2.5'], default_value='2.0', 
                         key='-FATOR_GALE-', size=(8,1), background_color=pal['INPUT_BG'])],
            ], font=('Segoe UI Semibold', 10), border_width=1, relief=sg.RELIEF_SOLID, 
               background_color=pal['PANEL'])],
            
            [sg.Frame('🎯 ESTRATÉGIAS', [
                [sg.Checkbox('Ciclos Probabilísticos', key='-ESTR_CICLOS-', default=True, 
                            text_color=pal['SUCCESS'])],
                [sg.Checkbox('Falsa Entrada', key='-ESTR_FALSA-', default=False, 
                            text_color=pal['INFO'])],
            ], font=('Segoe UI Semibold', 10), border_width=1, relief=sg.RELIEF_SOLID, 
               background_color=pal['PANEL'])],
        ]

        # Terminal em tempo real
        terminal_panel = [
            [sg.Frame('💻 TERMINAL EM TEMPO REAL', [
                [sg.Multiline(size=(80, 20), key='-TERMINAL-', 
                             autoscroll=True, disabled=True,
                             font=('Consolas', 10), 
                             background_color=pal['CONSOLE_BG'],
                             text_color=pal['CONSOLE_TEXT'],
                             border_width=0,
                             write_only=True,
                             auto_refresh=True)]
            ], font=('Segoe UI Semibold', 11), border_width=1, relief=sg.RELIEF_SOLID, 
               background_color=pal['PANEL'], expand_x=True, expand_y=True)]
        ]

        # Montagem final do layout com 2 colunas
        left_col = sg.Column(info_panel, vertical_alignment='top', element_justification='center')
        right_col = sg.Column(config_panel, vertical_alignment='top', element_justification='center', expand_x=True)
        
        layout = [
            header,
            control_panel,
            [sg.HorizontalSeparator(color=pal['BORDER'])],
            [left_col, right_col],
            [sg.HorizontalSeparator(color=pal['BORDER'])],
            terminal_panel,
            [sg.Text('Pronto', key='-SB-', text_color=pal['MUTE'], pad=(4, 2))]
        ]

        self.window = sg.Window(
            self.WINDOW_TITLE,
            layout,
            resizable=True,
            finalize=True,
            element_padding=(3, 2),
            margins=(5, 5),
            background_color=pal['BACKGROUND']
        )
        self.window.set_min_size((1000, 700))

    # ---------- FUNÇÕES DE CONEXÃO E TRADING ----------
    def conectar(self, email, senha, tipo_conta):
        self.log("🔄 Conectando à IQ Option...", 'info')
        
        try:
            self.api = IQ_Option(email, senha)
            status, reason = self.api.connect()
        except Exception as e:
            return False, str(e)

        if status:
            self.api.change_balance(tipo_conta)
            self.mercado_info['conectado'] = True
            self.mercado_info['tipo_conta'] = tipo_conta
            
            self.window['-STATUS-'].update('CONECTADO', text_color=self.palette['SUCCESS'])
            self.window['-TIPO_CONTA-'].update(tipo_conta, text_color=self.palette['INFO'])
            self.window['-START-'].update(disabled=False)
            self.window['-STATUS_CONTA-'].update(disabled=False)
            
            self.atualizar_saldo()
            return True, "Conectado"
        else:
            return False, reason

    def atualizar_saldo(self):
        try:
            saldo = self.api.get_balance()
            self.mercado_info['saldo'] = saldo
            self.mercado_info['ultima_atualizacao'] = datetime.now().strftime('%H:%M:%S')
            
            self.window['-SALDO_ATUAL-'].update(self._format_brl(saldo))
            self.window['-ULT_ATUAL-'].update(self.mercado_info['ultima_atualizacao'])
            
            if self.gerenciamento:
                self.gerenciamento.banca_atual = saldo
                
        except Exception as e:
            self.log(f"Erro ao atualizar saldo: {e}", 'error')

    def log(self, msg, level='info'):
        if self.logger:
            self.logger.log(msg, level)

    def verificar_resultado(self, ativo, direcao, stake, payout, timestamp_entrada):
        self.log("⏳ Aguardando fechamento da vela (62s)...", 'info')
        
        for i in range(62):
            time.sleep(1)
            if i % 10 == 0 and not self.api.check_connect():
                self.api.connect()

        self.log("📊 Buscando resultado...", 'info')

        for tentativa in range(3):
            try:
                velas = self.api.get_candles(ativo, 60, 3, time.time())
                vela_certa = next((v for v in velas if v['from'] == timestamp_entrada), None)
                
                if vela_certa:
                    abertura = float(vela_certa['open'])
                    fechamento = float(vela_certa['close'])
                    
                    if fechamento > abertura:  # CALL
                        if direcao.upper() == 'CALL':
                            lucro = round(stake * payout, 2)
                            self.log(f"💰 WIN! +R${lucro:.2f}", 'win')
                            return 'win', lucro
                        else:
                            self.log(f"📉 LOSS -R${stake:.2f}", 'loss')
                            return 'loss', -stake
                    elif fechamento < abertura:  # PUT
                        if direcao.upper() == 'PUT':
                            lucro = round(stake * payout, 2)
                            self.log(f"💰 WIN! +R${lucro:.2f}", 'win')
                            return 'win', lucro
                        else:
                            self.log(f"📉 LOSS -R${stake:.2f}", 'loss')
                            return 'loss', -stake
                    else:  # DOJI
                        self.log("⚖️ DOJI - Stake devolvido", 'warn')
                        return 'doji', 0.0
                
                time.sleep(1)
            except Exception as e:
                self.log(f"Erro na verificação: {e}", 'error')
        
        return 'loss', -stake

    def executar_ciclo(self, values):
        """Loop principal de trading"""
        try:
            # Configurações
            stake_base = float(values['-VALOR-'].replace(',', '.'))
            max_soros = int(values['-MAX_SOROS-'])
            max_gale = int(values['-MAX_GALE-'])
            fator_gale = float(values['-FATOR_GALE-'].replace(',', '.'))
            stop_win = float(values['-STOP_WIN-'].replace(',', '.'))
            stop_loss = float(values['-STOP_LOSS-'].replace(',', '.'))
            
            tf = 60 if 'M1' in values['-TF-'] else 300
            
            # Ativo
            ativo_base = values['-ATIVO-']
            is_otc = values['-IS_OTC-']
            ativo = ativo_base + "-OTC" if is_otc else ativo_base
            
            # Estratégias
            estrategias = {}
            if self.window['-ESTR_CICLOS-'].get():
                estrategias['Ciclos'] = StrategyCiclos(self.api, self.logger)
            if self.window['-ESTR_FALSA-'].get():
                estrategias['Falsa'] = StrategyFalsa(self.api, self.logger)

            if not estrategias:
                self.log("❌ Nenhuma estratégia ativa!", 'error')
                return

            # Inicializar gerenciamento
            self.gerenciamento = SorosGale(
                banca=self.mercado_info['saldo'],
                stake_base=stake_base,
                nivel_soros=max_soros,
                nivel_gale=max_gale,
                fator_gale=fator_gale
            )
            
            self.log(f"\n{'='*50}", 'info')
            self.log(f"🚀 ROBÔ INICIADO - {ativo}", 'signal')
            self.log(f"📊 Meta: +R${stop_win:.2f} | Stop: -R${stop_loss:.2f}", 'info')
            self.log(f"{'='*50}\n", 'info')

            lucro_acumulado = 0.0

            while self.is_running:
                # Verificar stops
                if lucro_acumulado >= stop_win:
                    self.log(f"\n🏆 META BATIDA! Lucro: R${lucro_acumulado:.2f}", 'win')
                    self.is_running = False
                    break

                if lucro_acumulado <= -stop_loss:
                    self.log(f"\n🛑 STOP LOSS ATINGIDO! Prejuízo: R${lucro_acumulado:.2f}", 'loss')
                    self.is_running = False
                    break

                # Sincronizar com o tempo
                now = time.time()
                segundos = time.localtime(now).tm_sec
                proxima_vela = int(now / 60) * 60 + 60

                if segundos not in [58, 59, 0]:
                    time.sleep(0.5)
                    continue

                # Verificar conexão
                if not self.api.check_connect():
                    self.log("⚠️ Reconectando...", 'warn')
                    self.api.connect()
                    time.sleep(2)
                    continue

                # Analisar cada estratégia
                for nome, estrategia in estrategias.items():
                    if not self.is_running:
                        break

                    direcao, motivo = estrategia.analisar(ativo, tf)

                    if direcao in ['call', 'put']:
                        # Calcular stake
                        stake = self.gerenciamento.calcular_stake()
                        info_entrada = self.gerenciamento.obter_info_entrada()
                        
                        # Obter payout
                        try:
                            payout_info = self.api.get_all_profit()
                            ativo_key = ativo.replace("-OTC", "")
                            payout = payout_info.get(ativo_key, {}).get('turbo', 0.85)
                        except:
                            payout = 0.85

                        # Log do sinal
                        self.log(f"\n{'▸'*40}", 'signal')
                        self.log(f"🚀 SINAL: {direcao.upper()} | {info_entrada} | R${stake:.2f} | {motivo}", 'signal')
                        
                        # Executar compra
                        status, id_ordem = self.api.buy(stake, ativo, direcao, 1)

                        if status:
                            resultado, lucro = self.verificar_resultado(
                                ativo, direcao, stake, payout, proxima_vela
                            )
                            
                            lucro_acumulado += lucro
                            self.gerenciamento.atualizar_resultado(resultado, lucro)
                            
                            # Atualizar contadores
                            stats = self.gerenciamento.get_stats()
                            self.window['-PLACAR-'].update(f"{stats['wins']}W - {stats['losses']}L - {stats['dojis']}D")
                            self.window['-WIN_RATE-'].update(f"{stats['win_rate']:.1f}%")
                            self.window['-SEQUENCIA-'].update(str(stats['sequencia']))
                            self.window['-TOTAL_TRADES-'].update(str(stats['total']))
                            self.window['-LUCRO-'].update(self._format_brl(lucro_acumulado))
                            
                            # Cor do lucro
                            cor = self.palette['SUCCESS'] if lucro_acumulado >= 0 else self.palette['ERROR']
                            self.window['-LUCRO-'].update(text_color=cor)
                            
                            # Atualizar saldo
                            self.atualizar_saldo()
                            
                            # Registrar na estratégia falsa
                            if nome == 'Falsa':
                                estrategia.registrar_resultado(ativo, direcao, resultado)
                        else:
                            self.log(f"❌ Erro na compra: {id_ordem}", 'error')

                # Pequena pausa
                time.sleep(1)

        except Exception as e:
            self.log(f"❌ Erro crítico: {e}", 'error')
            self.is_running = False

    # ---------- LOOP PRINCIPAL DA INTERFACE ----------
    def run(self):
        # Inicializar logger
        self.logger = RealTimeLogger(self._terminal_callback)
        
        # Mensagem de boas-vindas
        self.log("╔════════════════════════════════════╗", 'info')
        self.log("║   FRANCISX TRADING TERMINAL v8.0  ║", 'info')
        self.log("╚════════════════════════════════════╝", 'info')
        self.log("Aguardando conexão...\n", 'info')

        while True:
            event, values = self.window.read(timeout=50)
            
            # Atualizar terminal
            self._update_terminal()

            if event in (sg.WIN_CLOSED, 'SAIR'):
                break

            if event == '-LIMPAR_TERMINAL-':
                self.window['-TERMINAL-'].update('')

            if event == 'CONECTAR':
                email = values['-EMAIL-']
                senha = values['-SENHA-']
                tipo = 'PRACTICE' if values['-PRACTICE-'] else 'REAL'
                
                if not email or not senha:
                    self.log("❌ Email e senha obrigatórios!", 'error')
                    continue
                
                success, msg = self.conectar(email, senha, tipo)
                
                if success:
                    self.log(f"✅ Conectado com sucesso! Conta: {tipo}", 'success')
                else:
                    self.log(f"❌ Falha na conexão: {msg}", 'error')

            if event == '-STATUS_CONTA-':
                self.atualizar_saldo()
                self.log(f"💰 Saldo: {self._format_brl(self.mercado_info['saldo'])}", 'info')

            if event == '-START-':
                if not self.api:
                    self.log("❌ Conecte-se primeiro!", 'error')
                    continue
                
                self.is_running = True
                self.window['-START-'].update(disabled=True)
                self.window['-STOP-'].update(disabled=False)
                self.window['-STATUS-'].update('OPERANDO', text_color=self.palette['ACCENT2'])
                
                thread = threading.Thread(target=self.executar_ciclo, args=(values,), daemon=True)
                thread.start()

            if event == '-STOP-':
                self.is_running = False
                self.window['-START-'].update(disabled=False)
                self.window['-STOP-'].update(disabled=True)
                self.window['-STATUS-'].update('CONECTADO', text_color=self.palette['SUCCESS'])
                self.log("⏹️ Robô parado.", 'warn')

        # Cleanup
        if self.logger:
            self.logger.stop()
        self.window.close()


if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        handlers=[
            logging.FileHandler("terminal.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    app = ProBotDashboard()
    app.run()