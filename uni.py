# -*- coding: utf-8 -*-
import FreeSimpleGUI as sg
import time
import threading
import logging
import sys
from iqoptionapi.stable_api import IQ_Option
from collections import defaultdict
from datetime import datetime
import pandas as pd
import queue
from typing import Optional, List, Dict
from PIL import Image, ImageDraw, ImageFont
import io
import numpy as np
import random

# Configurar encoding
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Silenciar logs técnicos
logging.getLogger("iqoptionapi").setLevel(logging.CRITICAL)
logging.getLogger("websocket").setLevel(logging.CRITICAL)


# =========================================
# TEMA BLACK TOTAL
# =========================================
BLACK_THEME = {
    'BG_PRIMARY': '#000000',
    'BG_SECONDARY': '#000000',
    'BG_TERTIARY': '#000000',
    'BORDER': '#39FF14',
    'TEXT_PRIMARY': '#FFFFFF',
    'TEXT_SECONDARY': '#FFFFFF',
    'TEXT_MUTED': '#FFFFFF',
    'TERMINAL_GREEN': '#39FF14',
    'TERMINAL_DIM': '#00AA00',
    'ACCENT_SUCCESS': '#39FF14',
    'ACCENT_DANGER': '#FF4136',
    'ACCENT_WARNING': '#FFDC00',
    'ACCENT_INFO': '#7FDBFF',
    'TABLE_HEADER': '#000000',
    'TABLE_ROW1': '#000000',
    'TABLE_ROW2': '#000000',
    'BUTTON_BORDER': '#39FF14',
    'TITLE_GREEN': '#39FF14',
    
    # Cores dos cards
    'WIN_BG': '#00FF00',
    'WIN_TEXT': '#FFFFFF',
    'LOSS_BG': '#FF0000',
    'LOSS_TEXT': '#FFFFFF',
    'ASSERT_BG': '#FFFF00',
    'ASSERT_TEXT': '#000000',
    'TOTAL_BG': '#000000',
    'TOTAL_TEXT': '#FFFFFF',
    
    # Cores dos checkboxes
    'CHECK_ON': '#39FF14',   # Verde quando marcado
    'CHECK_OFF': '#000000',  # Preto quando desmarcado
}

# Ativos mais negociados mundialmente
ATIVOS_PRIORITARIOS = [
    'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD',
    'USDCHF', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY'
]

# =========================================
# SISTEMA DE BOTÕES
# =========================================
class RoundedButton:
    @staticmethod
    def create_button(text, key, width=120, height=36, radius=8, 
                     bg_color='#000000', text_color='#39FF14', 
                     font_size=10, border_color=None, border_width=0):
        
        img = Image.new('RGBA', (width * 2, height * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        draw.rounded_rectangle(
            [0, 0, width * 2 - 1, height * 2 - 1],
            radius=radius * 2,
            fill=bg_color
        )
        
        font = None
        try:
            font = ImageFont.truetype("calibri.ttf", font_size * 2)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", font_size * 2)
            except:
                font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (width * 2 - text_width) // 2
        y = (height * 2 - text_height) // 2 - 2
        
        draw.text((x, y), text, font=font, fill=text_color)
        
        img = img.resize((width, height), Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_bytes = buffer.getvalue()
        
        return sg.Button(
            '',
            image_data=img_bytes,
            button_color=(sg.theme_background_color(), sg.theme_background_color()),
            border_width=0,
            key=key,
            pad=(5, 5)
        )


# =========================================
# COMPONENTES UI
# =========================================
class StatCard:
    @staticmethod
    def create_win_card(title, value_key, initial_value="0"):
        layout = [
            [sg.Text(title.upper(), font=('Calibri', 9), 
                    text_color=BLACK_THEME['WIN_TEXT'], pad=(0, 0),
                    background_color=BLACK_THEME['WIN_BG'])],
            [sg.Text(initial_value, key=value_key, font=('Calibri Bold', 24), 
                    text_color=BLACK_THEME['WIN_TEXT'], pad=(0, 2),
                    background_color=BLACK_THEME['WIN_BG'])]
        ]
        
        return sg.Column(
            layout,
            background_color=BLACK_THEME['WIN_BG'],
            pad=(2, 2),
            element_justification='center',
            expand_x=True
        )
    
    @staticmethod
    def create_loss_card(title, value_key, initial_value="0"):
        layout = [
            [sg.Text(title.upper(), font=('Calibri', 9), 
                    text_color=BLACK_THEME['LOSS_TEXT'], pad=(0, 0),
                    background_color=BLACK_THEME['LOSS_BG'])],
            [sg.Text(initial_value, key=value_key, font=('Calibri Bold', 24), 
                    text_color=BLACK_THEME['LOSS_TEXT'], pad=(0, 2),
                    background_color=BLACK_THEME['LOSS_BG'])]
        ]
        
        return sg.Column(
            layout,
            background_color=BLACK_THEME['LOSS_BG'],
            pad=(2, 2),
            element_justification='center',
            expand_x=True
        )
    
    @staticmethod
    def create_assert_card(title, value_key, initial_value="0"):
        layout = [
            [sg.Text(title.upper(), font=('Calibri', 9), 
                    text_color=BLACK_THEME['ASSERT_TEXT'], pad=(0, 0),
                    background_color=BLACK_THEME['ASSERT_BG'])],
            [sg.Text(initial_value, key=value_key, font=('Calibri Bold', 24), 
                    text_color=BLACK_THEME['ASSERT_TEXT'], pad=(0, 2),
                    background_color=BLACK_THEME['ASSERT_BG'])]
        ]
        
        return sg.Column(
            layout,
            background_color=BLACK_THEME['ASSERT_BG'],
            pad=(2, 2),
            element_justification='center',
            expand_x=True
        )
    
    @staticmethod
    def create_total_card(title, value_key, initial_value="0"):
        layout = [
            [sg.Text(title.upper(), font=('Calibri', 9), 
                    text_color=BLACK_THEME['TOTAL_TEXT'], pad=(0, 0),
                    background_color=BLACK_THEME['TOTAL_BG'])],
            [sg.Text(initial_value, key=value_key, font=('Calibri Bold', 24), 
                    text_color=BLACK_THEME['TOTAL_TEXT'], pad=(0, 2),
                    background_color=BLACK_THEME['TOTAL_BG'])]
        ]
        
        return sg.Column(
            layout,
            background_color=BLACK_THEME['TOTAL_BG'],
            pad=(2, 2),
            element_justification='center',
            expand_x=True
        )


class InputGroup:
    @staticmethod
    def create_label(text, size=(12, 1)):
        return sg.Text(
            text, 
            font=('Calibri', 10),
            text_color=BLACK_THEME['TITLE_GREEN'],
            size=size,
            pad=(0, 3),
            background_color=BLACK_THEME['BG_PRIMARY']
        )
    
    @staticmethod
    def create_input(key, default="", password=False, size=(18, 1), readonly=False):
        """Input com borda verde"""
        return sg.Input(
            default,
            key=key,
            password_char='*' if password else '',
            size=size,
            font=('Calibri', 10),
            background_color=BLACK_THEME['BG_PRIMARY'],
            text_color=BLACK_THEME['TEXT_PRIMARY'],
            border_width=1,
            pad=(0, 3),
            readonly=readonly
        )


# =========================================
# LOGGER
# =========================================
class RealTimeLogger:
    def __init__(self, callback):
        self.callback = callback
        self.queue = queue.Queue()
        self.running = True
        self.thread = threading.Thread(target=self._process_queue, daemon=True)
        self.thread.start()
    
    def _process_queue(self):
        while self.running:
            try:
                msg = self.queue.get(timeout=0.1)
                if self.callback:
                    self.callback(msg)
            except queue.Empty:
                continue
    
    def log(self, msg: str, level: str = 'info'):
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        symbols = {
            'error': '>>',
            'success': '>>',
            'win': '$$',
            'loss': 'XX',
            'warn': '!!',
            'signal': '>>',
            'pattern': '::',
            'info': '--',
            'system': '=='
        }
        
        symbol = symbols.get(level, '--')
        formatted = f"[{timestamp}] {symbol} {msg}"
        self.queue.put((formatted, BLACK_THEME['TERMINAL_GREEN']))
        logging.info(f"[{level.upper()}] {msg}")
    
    def stop(self):
        self.running = False


# =========================================
# GERENCIADOR DE PERFORMANCE
# =========================================
class PerformanceTracker:
    def __init__(self):
        self.stats = {}
        self.ultima_atualizacao = time.time()
    
    def registrar_resultado(self, ativo, estrategia, resultado):
        if ativo not in self.stats:
            self.stats[ativo] = {}
        
        if estrategia not in self.stats[ativo]:
            self.stats[ativo][estrategia] = {'wins': 0, 'losses': 0, 'total': 0}
        
        if resultado == 'win':
            self.stats[ativo][estrategia]['wins'] += 1
        elif resultado == 'loss':
            self.stats[ativo][estrategia]['losses'] += 1
        
        self.stats[ativo][estrategia]['total'] += 1
        self.ultima_atualizacao = time.time()
    
    def get_assertividade(self, ativo, estrategia):
        if ativo in self.stats and estrategia in self.stats[ativo]:
            stats = self.stats[ativo][estrategia]
            if stats['total'] > 0:
                return (stats['wins'] / stats['total'] * 100)
        return 0
    
    def get_tabela_dados(self, ativos_filtro=None):
        dados = []
        
        for ativo in self.stats:
            if ativos_filtro and ativo not in ativos_filtro:
                continue
                
            for estrategia, stats in self.stats[ativo].items():
                if stats['total'] > 0:
                    assertividade = (stats['wins'] / stats['total'] * 100)
                    dados.append([
                        ativo,
                        estrategia,
                        f"{assertividade:.1f}%",
                        str(stats['total']),
                        stats['wins'],
                        stats['losses']
                    ])
        
        dados.sort(key=lambda x: float(x[2].replace('%', '')), reverse=True)
        return dados
    
    def get_melhores_ativos(self, limite=5):
        performance_ativos = {}
        
        for ativo in self.stats:
            total_wins = 0
            total_trades = 0
            
            for estrategia, stats in self.stats[ativo].items():
                total_wins += stats['wins']
                total_trades += stats['total']
            
            if total_trades >= 3:
                performance_ativos[ativo] = (total_wins / total_trades * 100, total_trades)
        
        melhores = sorted(performance_ativos.items(), key=lambda x: x[1][0], reverse=True)
        return [ativo for ativo, _ in melhores[:limite]]


# =========================================
# GERENCIAMENTO SOROS GALE
# =========================================
class SorosGale:
    def __init__(self, banca, stake_base, nivel_soros, nivel_gale, fator_gale=2.0):
        self.banca_atual = float(banca)
        self.stake_base = float(stake_base)
        self.max_soros = int(nivel_soros)
        self.max_gale = int(nivel_gale)
        self.fator_gale = float(fator_gale)

        self.nivel_atual_soros = 0
        self.nivel_atual_gale = 0
        self.ultimo_lucro = 0.0
        self.wins = 0
        self.losses = 0
        self.dojis = 0

    def calcular_stake(self):
        if self.banca_atual < 1.0: 
            return 0

        if self.nivel_atual_gale > 0:
            if self.nivel_atual_gale > self.max_gale:
                self.nivel_atual_gale = 0
                return self.stake_base
            return round(self.stake_base * (self.fator_gale ** self.nivel_atual_gale), 2)

        if self.nivel_atual_soros > 0:
            if self.nivel_atual_soros > self.max_soros:
                self.nivel_atual_soros = 0
                return self.stake_base
            return round(self.stake_base + self.ultimo_lucro, 2)

        return self.stake_base

    def atualizar_resultado(self, resultado, valor_real):
        self.banca_atual += valor_real

        if resultado == 'win':
            self.wins += 1
            self.ultimo_lucro = valor_real
            
            if self.nivel_atual_gale > 0:
                self.nivel_atual_gale = 0
                self.nivel_atual_soros = 1
            else:
                self.nivel_atual_soros += 1

        elif resultado == 'loss':
            self.losses += 1
            self.ultimo_lucro = 0
            self.nivel_atual_soros = 0
            self.nivel_atual_gale += 1
            
        elif resultado == 'doji':
            self.dojis += 1

    def get_stats(self):
        total = self.wins + self.losses + self.dojis
        win_rate = (self.wins / total * 100) if total > 0 else 0
        return {
            'wins': self.wins,
            'losses': self.losses,
            'dojis': self.dojis,
            'total': total,
            'win_rate': win_rate
        }


# =========================================
# ESTRATÉGIA: TENDÊNCIA POR VELAS
# =========================================
class StrategyTendencia:
    def __init__(self, api, logger):
        self.api = api
        self.logger = logger
        self.nome = "Tendencia"
        self.last_signal_time = {}
        
    def get_color(self, candle):
        if candle['close'] > candle['open']: return 1
        if candle['close'] < candle['open']: return -1
        return 0
    
    def analisar_tendencia(self, candles):
        if len(candles) < 10:
            return None, 0
        
        ultimas_5 = candles[-5:]
        cores = [self.get_color(c) for c in ultimas_5]
        
        verdes = sum(1 for c in cores if c == 1)
        vermelhas = sum(1 for c in cores if c == -1)
        
        sequencia_atual = 1
        max_sequencia = 1
        for i in range(1, len(cores)):
            if cores[i] == cores[i-1] and cores[i] != 0:
                sequencia_atual += 1
                max_sequencia = max(max_sequencia, sequencia_atual)
            else:
                sequencia_atual = 1
        
        ultima = cores[-1] if cores[-1] != 0 else 0
        
        if verdes >= 4 and max_sequencia >= 3:
            return "call", 85
        elif vermelhas >= 4 and max_sequencia >= 3:
            return "put", 85
        elif verdes >= 3 and ultima == 1:
            return "call", 70
        elif vermelhas >= 3 and ultima == -1:
            return "put", 70
        elif verdes > vermelhas and ultima == 1:
            return "call", 60
        elif vermelhas > verdes and ultima == -1:
            return "put", 60
        
        return None, 0
    
    def analisar(self, ativo, tf_segundos):
        try:
            candles = self.api.get_candles(ativo, tf_segundos, 30, time.time())
            if not candles or len(candles) < 10:
                return None, "WAIT"
            
            now = time.time()
            if ativo in self.last_signal_time and now - self.last_signal_time[ativo] < 60:
                return None, "COOLDOWN"
            
            direcao, confianca = self.analisar_tendencia(candles)
            
            if direcao:
                self.last_signal_time[ativo] = now
                return direcao, f"TEND{confianca}"
            
            return None, "NO_SIGNAL"
            
        except Exception as e:
            self.logger.log(f"Erro Tendencia: {e}", 'error')
            return None, "ERR"


# =========================================
# ESTRATÉGIA: CICLOS PROBABILÍSTICOS
# =========================================
class StrategyCiclos:
    def __init__(self, api, logger):
        self.api = api
        self.logger = logger
        self.nome = "Ciclos"
        self.last_pattern = {}
        self.last_signal_time = {}

    def get_color(self, candle):
        if candle['close'] > candle['open']: return 1
        if candle['close'] < candle['open']: return -1
        return 0

    def analisar(self, ativo, tf_segundos):
        try:
            candles = self.api.get_candles(ativo, tf_segundos, 120, time.time())
            if not candles or len(candles) < 20:
                return None, "WAIT"
            
            df = pd.DataFrame(candles)
            
            current_pattern = None
            for i in range(2, min(len(df) - 5, 100)): 
                idx0, idx1, idx2, idx3 = -i, -i-1, -i-2, -i-3
                
                h0 = self.get_color(df.iloc[idx0])
                h1 = self.get_color(df.iloc[idx1])
                h2 = self.get_color(df.iloc[idx2])
                h3 = self.get_color(df.iloc[idx3])
                
                if h0 == 0 or h1 == 0 or h2 == 0 or h3 == 0: continue

                if (h3 != h2) and (h2 == h1) and (h1 == h0):
                    current_pattern = 'AZUL'
                    break 
                
                elif (h3 != h2) and (h2 == h1) and (h1 != h0) and (h0 == h3):
                    current_pattern = 'ROSA'
                    break 

            if current_pattern:
                self.last_pattern[ativo] = current_pattern
            
            padrao_atual = self.last_pattern.get(ativo, 'WAIT')
            
            c3 = self.get_color(df.iloc[-1]) 
            c2 = self.get_color(df.iloc[-2]) 
            c1 = self.get_color(df.iloc[-3]) 

            if (c1 != c2) and (c2 == c3) and c1 != 0 and c2 != 0:
                now = time.time()
                if ativo in self.last_signal_time and now - self.last_signal_time[ativo] < 60:
                    return None, f"{padrao_atual}_COOLDOWN"
                
                if padrao_atual == 'AZUL' and c3 == -1:
                    self.last_signal_time[ativo] = now
                    return 'put', f"{padrao_atual}"
                elif padrao_atual == 'ROSA':
                    if c1 == 1:
                        self.last_signal_time[ativo] = now
                        return 'call', f"{padrao_atual}"
                    if c1 == -1:
                        self.last_signal_time[ativo] = now
                        return 'put', f"{padrao_atual}"

            return None, f"{padrao_atual}"
            
        except Exception as e:
            self.logger.log(f"Erro Ciclos: {e}", 'error')
            return None, "ERR"


# =========================================
# ESTRATÉGIA: FALSA ENTRADA
# =========================================
class StrategyFalsa:
    def __init__(self, api, logger):
        self.api = api
        self.logger = logger
        self.nome = "Falsa"
        self.ultima_direcao = {}
        self.contador = {}
        self.last_signal_time = {}

    def analisar(self, ativo, tf_segundos):
        try:
            candles = self.api.get_candles(ativo, tf_segundos, 10, time.time())
            if not candles or len(candles) < 5:
                return None, "WAIT"
            
            ultimas = candles[-3:]
            verdes = sum(1 for c in ultimas if c['close'] > c['open'])
            vermelhas = 3 - verdes
            
            if ativo not in self.contador:
                self.contador[ativo] = 0
                self.ultima_direcao[ativo] = None
            
            now = time.time()
            if ativo in self.last_signal_time and now - self.last_signal_time[ativo] < 60:
                return None, "COOLDOWN"
            
            if verdes == 3:
                if self.ultima_direcao[ativo] == 'call' and self.contador[ativo] < 2:
                    self.contador[ativo] += 1
                    self.last_signal_time[ativo] = now
                    return 'call', f"SEQ{self.contador[ativo]}"
                self.ultima_direcao[ativo] = 'call'
                self.contador[ativo] = 1
                self.last_signal_time[ativo] = now
                return 'call', "DIR"
                
            elif vermelhas == 3:
                if self.ultima_direcao[ativo] == 'put' and self.contador[ativo] < 2:
                    self.contador[ativo] += 1
                    self.last_signal_time[ativo] = now
                    return 'put', f"SEQ{self.contador[ativo]}"
                self.ultima_direcao[ativo] = 'put'
                self.contador[ativo] = 1
                self.last_signal_time[ativo] = now
                return 'put', "DIR"
            
            return None, f"{verdes}-{vermelhas}"
            
        except Exception as e:
            self.logger.log(f"Erro Falsa: {e}", 'error')
            return None, "ERR"
    
    def registrar_resultado(self, ativo, direcao, resultado):
        if resultado == 'loss':
            self.contador[ativo] = 0


# =========================================
# ESTRATÉGIA: TREND + PULLBACK
# =========================================
class StrategyTrendPullback:
    def __init__(self, api, logger):
        self.api = api
        self.logger = logger
        self.nome = "TrendPullback"
        self.last_signal_time = {}
        
    @staticmethod
    def _ema(values, period: int):
        if values is None or len(values) < period:
            return None
        values = np.asarray(values, dtype=float)
        alpha = 2.0 / (period + 1.0)
        ema = [values[0]]
        for v in values[1:]:
            ema.append((v - ema[-1]) * alpha + ema[-1])
        return np.asarray(ema, dtype=float)

    def analisar(self, ativo, tf_segundos):
        try:
            candles = self.api.get_candles(ativo, tf_segundos, 100, time.time())
            if not candles or len(candles) < 60:
                return None, "WAIT"
            
            closes = [float(c['close']) for c in candles]
            
            ema21 = self._ema(closes, 21)
            ema50 = self._ema(closes, 50)
            
            if ema21 is None or ema50 is None or len(ema21) < 5 or len(ema50) < 5:
                return None, "EMA_ERR"
            
            c0, c1, c2 = closes[-1], closes[-2], closes[-3]
            e21 = float(ema21[-1])
            e50 = float(ema50[-1])
            
            trend_up = e21 > e50
            trend_dn = e21 < e50
            
            price_ema_dist = abs(c0 - e21) / max(1e-9, abs(e21))
            near_ema = price_ema_dist <= 0.0030
            
            bullish = (c0 > c1) and (c1 < c2)
            bearish = (c0 < c1) and (c1 > c2)
            
            now = time.time()
            if ativo in self.last_signal_time and now - self.last_signal_time[ativo] < 60:
                return None, "COOLDOWN"
            
            if trend_up and near_ema and bullish:
                self.last_signal_time[ativo] = now
                return "call", "PULLBACK_UP"
                
            if trend_dn and near_ema and bearish:
                self.last_signal_time[ativo] = now
                return "put", "PULLBACK_DOWN"
            
            if trend_up and (c0 > c1 > c2):
                self.last_signal_time[ativo] = now
                return "call", "MOMENTUM_UP"
                
            if trend_dn and (c0 < c1 < c2):
                self.last_signal_time[ativo] = now
                return "put", "MOMENTUM_DOWN"
            
            return None, "NO_SIGNAL"
            
        except Exception as e:
            self.logger.log(f"Erro TrendPullback: {e}", 'error')
            return None, "ERR"


# =========================================
# SELETOR DE ATIVOS INTELIGENTE
# =========================================
class AtivoSelector:
    def __init__(self, api, logger, performance_tracker):
        self.api = api
        self.logger = logger
        self.performance = performance_tracker
        self.last_scan = 0
        self.ativos_prioritarios = ATIVOS_PRIORITARIOS
        
    def get_color(self, candle):
        if candle['close'] > candle['open']: return 1
        if candle['close'] < candle['open']: return -1
        return 0
    
    def avaliar_tendencia(self, ativo, tf_segundos=60):
        try:
            candles = self.api.get_candles(ativo, tf_segundos, 30, time.time())
            if not candles or len(candles) < 20:
                return 0
            
            closes = [float(c['close']) for c in candles]
            
            media_curta = np.mean(closes[-5:])
            media_longa = np.mean(closes[-20:])
            
            if media_curta > media_longa:
                forca = (media_curta - media_longa) / media_longa * 100
            else:
                forca = (media_longa - media_curta) / media_longa * 100
            
            ultimas_cores = [self.get_color(c) for c in candles[-10:]]
            sequencia_max = 1
            seq_atual = 1
            
            for i in range(1, len(ultimas_cores)):
                if ultimas_cores[i] == ultimas_cores[i-1] and ultimas_cores[i] != 0:
                    seq_atual += 1
                    sequencia_max = max(sequencia_max, seq_atual)
                else:
                    seq_atual = 1
            
            score = forca * 2 + sequencia_max * 5
            return min(100, score)
            
        except Exception as e:
            self.logger.log(f"Erro avaliar tendência {ativo}: {e}", 'error')
            return 0
    
    def get_todos_ativos_disponiveis(self, is_otc=True):
        try:
            todos_ativos = self.api.get_all_open_time()
            ativos = []
            
            for tipo in ['turbo', 'binary']:
                if tipo in todos_ativos:
                    for ativo, dados in todos_ativos[tipo].items():
                        if dados.get('open', False):
                            if is_otc and ('-OTC' in ativo or 'otc' in ativo.lower()):
                                ativos.append(ativo)
                            elif not is_otc and '-OTC' not in ativo and 'otc' not in ativo.lower():
                                ativos.append(ativo)
            
            if not ativos:
                ativos = [f"{p}-OTC" for p in self.ativos_prioritarios] if is_otc else self.ativos_prioritarios
            
            return sorted(ativos)
        except:
            return [f"{p}-OTC" for p in self.ativos_prioritarios] if is_otc else self.ativos_prioritarios
    
    def selecionar_melhores_ativos(self, lista_ativos, estrategias_ativas, tf_segundos=60, quantidade=3):
        self.logger.log(f"Selecionando ativos (prioritários + tendência)...", 'info')
        
        is_otc = any('-OTC' in a or 'otc' in a.lower() for a in lista_ativos[:5])
        
        ativos_prio_disponiveis = []
        for prio in self.ativos_prioritarios:
            ativo_formatado = f"{prio}-OTC" if is_otc else prio
            if ativo_formatado in lista_ativos:
                ativos_prio_disponiveis.append(ativo_formatado)
        
        self.logger.log(f"Ativos prioritários disponíveis: {len(ativos_prio_disponiveis)}", 'info')
        
        if len(ativos_prio_disponiveis) >= quantidade:
            selecionados = ativos_prio_disponiveis[:quantidade]
            self.logger.log(f"Usando ativos prioritários: {', '.join(selecionados)}", 'success')
            return selecionados
        
        selecionados = ativos_prio_disponiveis.copy()
        restantes = quantidade - len(selecionados)
        
        if restantes > 0:
            disponiveis = [a for a in lista_ativos if a not in selecionados]
            
            scores_tendencia = []
            for ativo in disponiveis[:30]:
                score = self.avaliar_tendencia(ativo, tf_segundos)
                if score > 30:
                    scores_tendencia.append((ativo, score))
                time.sleep(0.1)
            
            scores_tendencia.sort(key=lambda x: x[1], reverse=True)
            melhores_tendencia = [a for a, s in scores_tendencia[:restantes * 2]]
            
            if melhores_tendencia:
                random.shuffle(melhores_tendencia)
                selecionados.extend(melhores_tendencia[:restantes])
        
        while len(selecionados) < quantidade and disponiveis:
            ativo = random.choice(disponiveis)
            if ativo not in selecionados:
                selecionados.append(ativo)
        
        self.logger.log(f"Ativos selecionados: {', '.join(selecionados[:quantidade])}", 'success')
        return selecionados[:quantidade]


# =========================================
# INTERFACE PRINCIPAL
# =========================================
class FrancisXDashboard:
    def __init__(self):
        self.theme = BLACK_THEME
        self.api = None
        self.is_running = False
        self.logger = None
        self.terminal_queue = queue.Queue()
        self.selector = None
        self.performance = PerformanceTracker()
        self.estrategias = {}
        
        self.saldo_inicial = 0
        self.lucro_sessao = 0
        self.wins = 0
        self.losses = 0
        self.dojis = 0
        
        self.window = None
        self.todos_ativos = []
        self._build_layout()

    def _format_brl(self, value: float) -> str:
        return f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    def _terminal_callback(self, msg_tuple):
        self.terminal_queue.put(msg_tuple)

    def _update_terminal(self):
        try:
            while True:
                msg, color = self.terminal_queue.get_nowait()
                if self.window and '-REGISTRO-' in self.window.AllKeysDict:
                    current = self.window['-REGISTRO-'].get()
                    
                    if isinstance(current, tuple):
                        current = current[0] if len(current) > 0 else ""
                    elif current is None:
                        current = ""
                    else:
                        current = str(current)
                    
                    lines = current.split('\n') if current else []
                    
                    if len(lines) > 200:
                        lines = lines[-200:]
                    
                    lines.append(str(msg))
                    
                    new_text = '\n'.join(lines)
                    self.window['-REGISTRO-'].update(new_text)
                    self.window['-REGISTRO-'].update(text_color=self.theme['TERMINAL_GREEN'])
                    
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Erro terminal: {e}")

    def _update_performance_table(self):
        if not self.window or '-TABLE-' not in self.window.AllKeysDict:
            return
        
        ativos_atuais = []
        if hasattr(self, 'melhores_ativos'):
            ativos_atuais = self.melhores_ativos
        
        dados = self.performance.get_tabela_dados(ativos_atuais if ativos_atuais else None)
        
        valores_tabela = []
        for row in dados[:15]:
            valores_tabela.append(row)
        
        self.window['-TABLE-'].update(values=valores_tabela)

    def _atualizar_dashboard(self):
        if not self.window:
            return
            
        self.window['-SALDO_INICIAL-'].update(self._format_brl(self.saldo_inicial))
        if self.api:
            self.window['-SALDO_ATUAL-'].update(self._format_brl(self.api.get_balance()))
        self.window['-LUCRO-'].update(self._format_brl(self.lucro_sessao))
        
        cor_lucro = self.theme['TERMINAL_GREEN'] if self.lucro_sessao >= 0 else self.theme['ACCENT_DANGER']
        self.window['-LUCRO-'].update(text_color=cor_lucro)
        
        self.window['-WINS-'].update(str(self.wins))
        self.window['-LOSSES-'].update(str(self.losses))
        
        total = self.wins + self.losses
        self.window['-TOTAL-'].update(str(total))
        
        if total > 0:
            taxa = (self.wins / total * 100)
            self.window['-ASSERTIVIDADE-'].update(f"{taxa:.1f}%")
        else:
            self.window['-ASSERTIVIDADE-'].update("0.0%")
        
        self._update_performance_table()

    def _build_layout(self):
        # ===== HEADER =====
        header = [
            sg.Column([
                [sg.Text('FRANCISX', font=('Calibri Bold', 22), 
                        text_color=self.theme['TITLE_GREEN'],
                        background_color=self.theme['BG_PRIMARY']),
                 sg.Text('BLACK', font=('Calibri Light', 22), 
                        text_color=self.theme['TERMINAL_GREEN'],
                        background_color=self.theme['BG_PRIMARY']),
                 sg.Push(),
                 sg.Text('[', font=('Calibri', 12), 
                        text_color=self.theme['TEXT_PRIMARY'],
                        background_color=self.theme['BG_PRIMARY']),
                 sg.Text('PARADO', font=('Calibri Bold', 11), 
                        text_color=self.theme['TEXT_PRIMARY'],
                        key='-STATUS-',
                        background_color=self.theme['BG_PRIMARY']),
                 sg.Text(']', font=('Calibri', 12), 
                        text_color=self.theme['TEXT_PRIMARY'],
                        background_color=self.theme['BG_PRIMARY']),
                 sg.Text('DEMO', font=('Calibri', 11), 
                        text_color=self.theme['TITLE_GREEN'],
                        key='-TIPO_CONTA-',
                        background_color=self.theme['BG_PRIMARY'])]
            ], background_color=self.theme['BG_PRIMARY'], pad=(20, 10), expand_x=True)
        ]

        # ===== BOTÕES SUPERIORES =====
        btn_conectar = RoundedButton.create_button(
            'CONECTAR', 'CONECTAR', width=110, height=34,
            text_color='#39FF14'
        )
        btn_iniciar = RoundedButton.create_button(
            'INICIAR', '-START-', width=110, height=34,
            text_color='#39FF14'
        )
        btn_parar = RoundedButton.create_button(
            'PARAR', '-STOP-', width=110, height=34,
            text_color='#39FF14'
        )
        btn_saldo = RoundedButton.create_button(
            'SALDO', '-STATUS_CONTA-', width=100, height=34,
            text_color='#39FF14'
        )
        btn_limpar = RoundedButton.create_button(
            'LIMPAR', '-LIMPAR_LOG-', width=100, height=34,
            text_color='#39FF14'
        )
        btn_scan = RoundedButton.create_button(
            'SCAN', '-SCAN_ATIVOS-', width=100, height=34,
            text_color='#39FF14'
        )

        control_panel = [
            sg.Column([
                [btn_conectar, btn_iniciar, btn_parar, btn_saldo, btn_limpar, btn_scan]
            ], background_color=self.theme['BG_PRIMARY'], pad=(20, 5))
        ]

        # ===== SALDOS =====
        saldo_section = sg.Column([
            [sg.Column([
                [sg.Text('BANCA INICIAL', font=('Calibri', 9), 
                        text_color=self.theme['TITLE_GREEN'],
                        background_color=self.theme['BG_PRIMARY'])],
                [sg.Text('R$ 0,00', key='-SALDO_INICIAL-', font=('Calibri Bold', 28), 
                        text_color=self.theme['TEXT_PRIMARY'],
                        background_color=self.theme['BG_PRIMARY'])]
            ], background_color=self.theme['BG_PRIMARY'], element_justification='center'),
             
             sg.Push(),
             
             sg.Column([
                [sg.Text('SALDO ATUAL', font=('Calibri', 9), 
                        text_color=self.theme['TITLE_GREEN'],
                        background_color=self.theme['BG_PRIMARY'])],
                [sg.Text('R$ 0,00', key='-SALDO_ATUAL-', font=('Calibri Bold', 28), 
                        text_color=self.theme['TEXT_PRIMARY'],
                        background_color=self.theme['BG_PRIMARY'])]
            ], background_color=self.theme['BG_PRIMARY'], element_justification='center'),
             
             sg.Push(),
             
             sg.Column([
                [sg.Text('RESULTADO', font=('Calibri', 9), 
                        text_color=self.theme['TITLE_GREEN'],
                        background_color=self.theme['BG_PRIMARY'])],
                [sg.Text('R$ 0,00', key='-LUCRO-', font=('Calibri Bold', 28), 
                        text_color=self.theme['TERMINAL_GREEN'],
                        background_color=self.theme['BG_PRIMARY'])]
            ], background_color=self.theme['BG_PRIMARY'], element_justification='center')]
        ], background_color=self.theme['BG_PRIMARY'], pad=(20, 15), expand_x=True)

        # ===== ESTATISTICAS =====
        stats_section = sg.Column([
            [StatCard.create_win_card('WINS', '-WINS-', '0'),
             StatCard.create_loss_card('LOSSES', '-LOSSES-', '0'),
             StatCard.create_assert_card('ASSERTIVIDADE', '-ASSERTIVIDADE-', '0.0%'),
             StatCard.create_total_card('OPERAÇÕES', '-TOTAL-', '0')]
        ], background_color=self.theme['BG_PRIMARY'], pad=(2, 2), expand_x=True)

        # ===== CONFIGURACOES =====
        config_left = sg.Column([
            [InputGroup.create_label('Email')],
            [InputGroup.create_input('-EMAIL-', size=(25, 1))],
            [InputGroup.create_label('Senha')],
            [InputGroup.create_input('-SENHA-', password=True, size=(25, 1))],
            [sg.Radio('DEMO', "R1", default=True, key='-PRACTICE-', 
                     text_color=self.theme['TITLE_GREEN'],
                     background_color=self.theme['BG_PRIMARY'],
                     font=('Calibri', 10)),
             sg.Radio('REAL', "R1", key='-REAL-', 
                     text_color=self.theme['TITLE_GREEN'],
                     background_color=self.theme['BG_PRIMARY'],
                     font=('Calibri', 10))]
        ], background_color=self.theme['BG_PRIMARY'], pad=(10, 5))

        config_center = sg.Column([
            [InputGroup.create_label('Ativo', size=(10, 1)),
             sg.Combo([], default_value='AUTO-SCAN', key='-ATIVO-', size=(14, 1),
                     background_color=self.theme['BG_PRIMARY'], 
                     text_color=self.theme['TEXT_PRIMARY'],
                     font=('Calibri', 10),
                     readonly=False,
                     button_background_color=self.theme['BG_PRIMARY'])],
            [InputGroup.create_label('Timeframe', size=(10, 1)),
             sg.Combo(['M1 (1 min)', 'M5 (5 min)'], default_value='M1 (1 min)', 
                     key='-TF-', size=(14, 1),
                     background_color=self.theme['BG_PRIMARY'],
                     text_color=self.theme['TEXT_PRIMARY'],
                     font=('Calibri', 10),
                     readonly=True,
                     button_background_color=self.theme['BG_PRIMARY'])],
            [sg.Checkbox('OTC', key='-IS_OTC-', default=True, 
                        text_color=self.theme['TITLE_GREEN'],
                        background_color=self.theme['BG_PRIMARY'],
                        font=('Calibri', 10),
                        checkbox_color=self.theme['CHECK_ON'])]
        ], background_color=self.theme['BG_PRIMARY'], pad=(10, 5))

        config_right = sg.Column([
            [InputGroup.create_label('Valor Entrada', size=(14, 1)),
             InputGroup.create_input('-VALOR-', default='2.00', size=(12, 1))],
            [InputGroup.create_label('Stop Win', size=(14, 1)),
             InputGroup.create_input('-STOP_WIN-', default='50.00', size=(12, 1))],
            [InputGroup.create_label('Stop Loss', size=(14, 1)),
             InputGroup.create_input('-STOP_LOSS-', default='25.00', size=(12, 1))]
        ], background_color=self.theme['BG_PRIMARY'], pad=(10, 5))

        config_panel = sg.Column([
            [config_left, config_center, config_right]
        ], background_color=self.theme['BG_PRIMARY'], pad=(20, 5), expand_x=True)

        # ===== GERENCIAMENTO E ESTRATÉGIAS =====
        ger_left = sg.Column([
            [InputGroup.create_label('Max Soros', size=(11, 1)),
             sg.Combo(['0', '1', '2', '3', '4', '5'], default_value='2', 
                     key='-MAX_SOROS-', size=(10, 1),
                     background_color=self.theme['BG_PRIMARY'],
                     text_color=self.theme['TEXT_PRIMARY'],
                     font=('Calibri', 10),
                     readonly=True,
                     button_background_color=self.theme['BG_PRIMARY'])],
            [InputGroup.create_label('Max Gale', size=(11, 1)),
             sg.Combo(['0', '1', '2', '3'], default_value='2', 
                     key='-MAX_GALE-', size=(10, 1),
                     background_color=self.theme['BG_PRIMARY'],
                     text_color=self.theme['TEXT_PRIMARY'],
                     font=('Calibri', 10),
                     readonly=True,
                     button_background_color=self.theme['BG_PRIMARY'])],
            [InputGroup.create_label('Fator Gale', size=(11, 1)),
             sg.Combo(['1.5', '2.0', '2.3', '2.5'], default_value='2.0', 
                     key='-FATOR_GALE-', size=(10, 1),
                     background_color=self.theme['BG_PRIMARY'],
                     text_color=self.theme['TEXT_PRIMARY'],
                     font=('Calibri', 10),
                     readonly=True,
                     button_background_color=self.theme['BG_PRIMARY'])]
        ], background_color=self.theme['BG_PRIMARY'], pad=(10, 5))

        ger_center = sg.Column([
            [sg.Text('ESTRATÉGIAS', font=('Calibri Bold', 11), 
                    text_color=self.theme['TITLE_GREEN'],
                    background_color=self.theme['BG_PRIMARY'])],
            [sg.Checkbox('Ciclos Probabilisticos', key='-ESTR_CICLOS-', default=True,
                        text_color=self.theme['TITLE_GREEN'],
                        background_color=self.theme['BG_PRIMARY'],
                        font=('Calibri', 10),
                        checkbox_color=self.theme['CHECK_ON'])],
            [sg.Checkbox('Falsa Entrada', key='-ESTR_FALSA-', default=False,
                        text_color=self.theme['TITLE_GREEN'],
                        background_color=self.theme['BG_PRIMARY'],
                        font=('Calibri', 10),
                        checkbox_color=self.theme['CHECK_OFF'])],
            [sg.Checkbox('Trend + Pullback', key='-ESTR_TREND-', default=True,
                        text_color=self.theme['TITLE_GREEN'],
                        background_color=self.theme['BG_PRIMARY'],
                        font=('Calibri', 10),
                        checkbox_color=self.theme['CHECK_ON'])],
            [sg.Checkbox('Tendência (Velas)', key='-ESTR_TENDENCIA-', default=True,
                        text_color=self.theme['TITLE_GREEN'],
                        background_color=self.theme['BG_PRIMARY'],
                        font=('Calibri', 10),
                        checkbox_color=self.theme['CHECK_ON'])]
        ], background_color=self.theme['BG_PRIMARY'], pad=(10, 5))

        ger_right = sg.Column([
            [InputGroup.create_label('Qtd Ativos', size=(12, 1)),
             sg.Combo(['1', '2', '3', '4', '5'], default_value='3', 
                     key='-QTD_ATIVOS-', size=(8, 1),
                     background_color=self.theme['BG_PRIMARY'],
                     text_color=self.theme['TEXT_PRIMARY'],
                     font=('Calibri', 10),
                     readonly=True,
                     button_background_color=self.theme['BG_PRIMARY'])],
            [InputGroup.create_label('Payout Min %', size=(12, 1)),
             InputGroup.create_input('-PAYOUT-', default='70', size=(8, 1))],
            [sg.Text('Ativos Ativos:', font=('Calibri', 9), 
                    text_color=self.theme['TITLE_GREEN'],
                    background_color=self.theme['BG_PRIMARY'])],
            [sg.Text('Nenhum', key='-ATIVOS_ATIVOS-', font=('Calibri', 9), 
                    text_color=self.theme['TEXT_PRIMARY'],
                    background_color=self.theme['BG_PRIMARY'])]
        ], background_color=self.theme['BG_PRIMARY'], pad=(10, 5))

        ger_panel = sg.Column([
            [ger_left, ger_center, ger_right]
        ], background_color=self.theme['BG_PRIMARY'], pad=(20, 5), expand_x=True)

        # ===== ÁREA PRINCIPAL =====
        log_column = sg.Column([
            [sg.Text('TERMINAL', font=('Calibri Bold', 11), 
                    text_color=self.theme['TITLE_GREEN'],
                    background_color=self.theme['BG_PRIMARY'])],
            [sg.Multiline(
                size=(70, 20), 
                key='-REGISTRO-',
                autoscroll=True,
                disabled=True,
                font=('Consolas', 9),
                background_color='#000000',
                text_color=self.theme['TERMINAL_GREEN'],
                border_width=0,
                write_only=True,
                pad=(5, 5),
                default_text='',
                no_scrollbar=False,
                expand_x=True,
                expand_y=True
            )]
        ], background_color=self.theme['BG_PRIMARY'], pad=(10, 5), expand_x=True, expand_y=True)

        table_column = sg.Column([
            [sg.Text('PERFORMANCE POR ATIVO', font=('Calibri Bold', 11), 
                    text_color=self.theme['TITLE_GREEN'],
                    background_color=self.theme['BG_PRIMARY'])],
            [sg.Table(
                values=[],
                headings=['Ativo', 'Estratégia', '%', 'Trades', 'W', 'L'],
                auto_size_columns=False,
                col_widths=[12, 12, 6, 6, 4, 4],
                key='-TABLE-',
                background_color=self.theme['BG_PRIMARY'],
                text_color=self.theme['TEXT_PRIMARY'],
                header_background_color=self.theme['BG_PRIMARY'],
                header_text_color=self.theme['TITLE_GREEN'],
                font=('Consolas', 9),
                justification='center',
                num_rows=20,
                alternating_row_color=self.theme['BG_PRIMARY'],
                hide_vertical_scroll=False,
                expand_x=True,
                expand_y=True,
                enable_events=True,
                select_mode=sg.TABLE_SELECT_MODE_BROWSE
            )]
        ], background_color=self.theme['BG_PRIMARY'], pad=(10, 5), expand_x=True, expand_y=True)

        main_panel = sg.Column([
            [log_column, sg.VerticalSeparator(color=self.theme['TITLE_GREEN']), table_column]
        ], background_color=self.theme['BG_PRIMARY'], pad=(10, 10), expand_x=True, expand_y=True)

        # ===== RODAPE =====
        footer = [
            sg.Column([
                [sg.Text('Pronto', key='-SB-', font=('Calibri', 9), 
                        text_color=self.theme['TEXT_PRIMARY'],
                        background_color=self.theme['BG_PRIMARY'])]
            ], background_color=self.theme['BG_PRIMARY'], pad=(20, 5))
        ]

        # Montagem final
        layout = [
            header,
            control_panel,
            [sg.HorizontalSeparator(color=self.theme['TITLE_GREEN'])],
            [saldo_section],
            [stats_section],
            [sg.HorizontalSeparator(color=self.theme['TITLE_GREEN'])],
            [config_panel],
            [ger_panel],
            [sg.HorizontalSeparator(color=self.theme['TITLE_GREEN'])],
            [main_panel],
            footer
        ]

        self.window = sg.Window(
            'FRANCISX BLACK - PERFORMANCE ANALYTICS',
            layout,
            resizable=True,
            finalize=True,
            element_padding=(0, 0),
            margins=(0, 0),
            background_color=self.theme['BG_PRIMARY'],
            icon=None,
            element_justification='left'
        )
        self.window.set_min_size((1200, 850))
        
        if self.todos_ativos:
            self.window['-ATIVO-'].update(values=['AUTO-SCAN'] + self.todos_ativos)

    def log(self, msg, level='info'):
        if self.logger:
            self.logger.log(msg, level)

    def verificar_resultado(self, ativo, direcao, stake, payout, timestamp_entrada):
        self.log("Aguardando fechamento (62s)...", 'info')
        
        for i in range(62):
            time.sleep(1)
            if i % 10 == 0 and not self.api.check_connect():
                self.api.connect()

        self.log("Buscando resultado...", 'info')

        for tentativa in range(3):
            try:
                velas = self.api.get_candles(ativo, 60, 3, time.time())
                vela_certa = next((v for v in velas if v['from'] == timestamp_entrada), None)
                
                if vela_certa:
                    abertura = float(vela_certa['open'])
                    fechamento = float(vela_certa['close'])
                    
                    if fechamento > abertura:
                        if direcao.upper() == 'CALL':
                            lucro = round(stake * payout, 2)
                            self.log(f"WIN +R${lucro:.2f}", 'win')
                            return 'win', lucro
                        else:
                            self.log(f"LOSS -R${stake:.2f}", 'loss')
                            return 'loss', -stake
                    elif fechamento < abertura:
                        if direcao.upper() == 'PUT':
                            lucro = round(stake * payout, 2)
                            self.log(f"WIN +R${lucro:.2f}", 'win')
                            return 'win', lucro
                        else:
                            self.log(f"LOSS -R${stake:.2f}", 'loss')
                            return 'loss', -stake
                    else:
                        self.log("DOJI - Stake devolvido", 'warn')
                        return 'doji', 0.0
                
                time.sleep(1)
            except Exception as e:
                self.log(f"Erro: {e}", 'error')
        
        return 'loss', -stake

    def scan_ativos(self, values):
        if not self.api:
            self.log("Conecte-se primeiro!", 'error')
            return
        
        if not self.selector:
            self.selector = AtivoSelector(self.api, self.logger, self.performance)
        
        self.log("Iniciando scan de ativos (prioritários + tendência)...", 'system')
        
        estrategias_ativas = []
        if values['-ESTR_CICLOS-']:
            estrategias_ativas.append('Ciclos')
        if values['-ESTR_FALSA-']:
            estrategias_ativas.append('Falsa')
        if values['-ESTR_TREND-']:
            estrategias_ativas.append('TrendPullback')
        if values['-ESTR_TENDENCIA-']:
            estrategias_ativas.append('Tendencia')
        
        if not estrategias_ativas:
            self.log("Selecione pelo menos uma estratégia!", 'error')
            return
        
        is_otc = values['-IS_OTC-']
        self.todos_ativos = self.selector.get_todos_ativos_disponiveis(is_otc)
        
        self.window['-ATIVO-'].update(values=['AUTO-SCAN'] + self.todos_ativos)
        
        tf = 60 if 'M1' in values['-TF-'] else 300
        qtd = int(values['-QTD_ATIVOS-'])
        
        self.melhores_ativos = self.selector.selecionar_melhores_ativos(
            self.todos_ativos, estrategias_ativas, tf, qtd
        )
        
        if self.melhores_ativos:
            self.window['-ATIVOS_ATIVOS-'].update(', '.join(self.melhores_ativos[:3]))
            self.log(f"Scan concluído! Ativos: {', '.join(self.melhores_ativos)}", 'success')
        else:
            self.log("Usando ativos prioritários...", 'warn')
            self.melhores_ativos = [f"{p}-OTC" if is_otc else p for p in ATIVOS_PRIORITARIOS[:qtd]]
            self.window['-ATIVOS_ATIVOS-'].update(', '.join(self.melhores_ativos[:3]))

    def executar_ciclo(self, values):
        try:
            stake_base = float(values['-VALOR-'].replace(',', '.'))
            max_soros = int(values['-MAX_SOROS-'])
            max_gale = int(values['-MAX_GALE-'])
            fator_gale = float(values['-FATOR_GALE-'].replace(',', '.'))
            stop_win = float(values['-STOP_WIN-'].replace(',', '.'))
            stop_loss = float(values['-STOP_LOSS-'].replace(',', '.'))
            payout_min = float(values['-PAYOUT-']) / 100
            qtd_ativos = int(values['-QTD_ATIVOS-'])
            
            tf = 60 if 'M1' in values['-TF-'] else 300
            
            estrategias = {}
            if values['-ESTR_CICLOS-']:
                estrategias['Ciclos'] = StrategyCiclos(self.api, self.logger)
            if values['-ESTR_FALSA-']:
                estrategias['Falsa'] = StrategyFalsa(self.api, self.logger)
            if values['-ESTR_TREND-']:
                estrategias['TrendPullback'] = StrategyTrendPullback(self.api, self.logger)
            if values['-ESTR_TENDENCIA-']:
                estrategias['Tendencia'] = StrategyTendencia(self.api, self.logger)

            if not estrategias:
                self.log("Nenhuma estrategia ativa!", 'error')
                return

            ativo_escolhido = values['-ATIVO-']
            is_otc = values['-IS_OTC-']
            
            if ativo_escolhido == 'AUTO-SCAN':
                if not hasattr(self, 'melhores_ativos') or not self.melhores_ativos:
                    self.log("Executando scan automático...", 'info')
                    self.scan_ativos(values)
                
                ativos_para_operar = getattr(self, 'melhores_ativos', [])
                if not ativos_para_operar:
                    ativos_para_operar = [f"{p}-OTC" if is_otc else p for p in ATIVOS_PRIORITARIOS[:qtd_ativos]]
            else:
                ativo_base = ativo_escolhido
                ativos_para_operar = [ativo_base + "-OTC" if is_otc and "-OTC" not in ativo_base else ativo_base]
            
            ativos_para_operar = ativos_para_operar[:qtd_ativos]
            self.log(f"Operando em: {', '.join(ativos_para_operar)}", 'system')

            self.gerenciamento = SorosGale(
                banca=self.api.get_balance(),
                stake_base=stake_base,
                nivel_soros=max_soros,
                nivel_gale=max_gale,
                fator_gale=fator_gale
            )
            
            if not self.selector:
                self.selector = AtivoSelector(self.api, self.logger, self.performance)
            
            self.log("="*50, 'system')
            self.log(f"ROBO INICIADO - {len(ativos_para_operar)} ativos", 'signal')
            self.log(f"Estratégias: {', '.join(estrategias.keys())}", 'info')
            self.log(f"Meta: +R${stop_win:.2f} | Stop: -R${stop_loss:.2f}", 'info')
            self.log("="*50, 'system')

            ultimo_scan = time.time()
            
            while self.is_running:
                if self.lucro_sessao >= stop_win:
                    self.log(f"META BATIDA! Lucro: R${self.lucro_sessao:.2f}", 'win')
                    self.is_running = False
                    break

                if self.lucro_sessao <= -stop_loss:
                    self.log(f"STOP LOSS! Prejuizo: R${self.lucro_sessao:.2f}", 'loss')
                    self.is_running = False
                    break

                if time.time() - ultimo_scan > 1800 and ativo_escolhido == 'AUTO-SCAN':
                    self.log("Reavaliando ativos...", 'info')
                    self.scan_ativos(values)
                    ativos_para_operar = getattr(self, 'melhores_ativos', ativos_para_operar)[:qtd_ativos]
                    ultimo_scan = time.time()

                now = time.time()
                segundos = time.localtime(now).tm_sec

                if segundos not in [58, 59, 0]:
                    time.sleep(0.5)
                    continue

                if not self.api.check_connect():
                    self.log("Reconectando...", 'warn')
                    self.api.connect()
                    time.sleep(2)
                    continue

                for ativo in ativos_para_operar:
                    if not self.is_running:
                        break

                    for nome, estrategia in estrategias.items():
                        if not self.is_running:
                            break

                        try:
                            direcao, motivo = estrategia.analisar(ativo, tf)

                            if direcao in ['call', 'put']:
                                stake = self.gerenciamento.calcular_stake()
                                
                                try:
                                    payout_info = self.api.get_all_profit()
                                    ativo_key = ativo.replace("-OTC", "").replace("-otc", "")
                                    payout = payout_info.get(ativo_key, {}).get('turbo', 0.85)
                                    if payout < payout_min:
                                        continue
                                except:
                                    payout = 0.85

                                self.log(f"{'='*40}", 'signal')
                                self.log(f"{ativo} | {direcao.upper()} | R${stake:.2f} | {nome} | {motivo}", 'signal')
                                
                                status, id_ordem = self.api.buy(stake, ativo, direcao, 1)

                                if status:
                                    proxima_vela = int(now / 60) * 60 + 60
                                    resultado, lucro = self.verificar_resultado(
                                        ativo, direcao, stake, payout, proxima_vela
                                    )
                                    
                                    self.lucro_sessao += lucro
                                    self.gerenciamento.atualizar_resultado(resultado, lucro)
                                    
                                    self.performance.registrar_resultado(ativo, nome, resultado)
                                    
                                    stats = self.gerenciamento.get_stats()
                                    self.wins = stats['wins']
                                    self.losses = stats['losses']
                                    self.dojis = stats['dojis']
                                    
                                    self._atualizar_dashboard()
                                    
                                    if nome == 'Falsa' and hasattr(estrategia, 'registrar_resultado'):
                                        estrategia.registrar_resultado(ativo, direcao, resultado)
                                else:
                                    self.log(f"Erro na compra {ativo}: {id_ordem}", 'error')
                        except Exception as e:
                            self.log(f"Erro em {ativo}/{nome}: {e}", 'error')
                            continue

                time.sleep(1)

        except Exception as e:
            self.log(f"Erro fatal: {e}", 'error')
            self.is_running = False

    def run(self):
        self.logger = RealTimeLogger(self._terminal_callback)
        
        self.log("FRANCISX BLACK EDITION v12.0 - CHECKBOXES PADRÃO", 'system')
        self.log("Aguardando conexao...", 'info')
        self.melhores_ativos = []

        while True:
            event, values = self.window.read(timeout=50)
            
            self._update_terminal()

            if event in (sg.WIN_CLOSED, 'SAIR'):
                break

            if event == '-LIMPAR_LOG-':
                self.window['-REGISTRO-'].update('')

            if event == '-SCAN_ATIVOS-':
                self.scan_ativos(values)
                
            if event == '-TABLE-':
                if values['-TABLE-'] and len(values['-TABLE-']) > 0:
                    selected_row = values['-TABLE-'][0]
                    dados_tabela = self.window['-TABLE-'].get()
                    if selected_row < len(dados_tabela):
                        ativo_selecionado = dados_tabela[selected_row][0]
                        self.window['-ATIVO-'].update(value=ativo_selecionado)
                        self.log(f"Ativo selecionado: {ativo_selecionado}", 'info')

            if event == 'CONECTAR':
                email = values['-EMAIL-']
                senha = values['-SENHA-']
                tipo = 'PRACTICE' if values['-PRACTICE-'] else 'REAL'
                
                if not email or not senha:
                    self.log("Email e senha obrigatorios!", 'error')
                    continue
                
                try:
                    self.api = IQ_Option(email, senha)
                    status, reason = self.api.connect()
                    
                    if status:
                        self.api.change_balance(tipo)
                        self.saldo_inicial = self.api.get_balance()
                        
                        self.window['-STATUS-'].update('CONECTADO')
                        self.window['-STATUS-'].update(text_color=self.theme['TITLE_GREEN'])
                        self.window['-TIPO_CONTA-'].update(tipo)
                        self.window['-START-'].update(disabled=False)
                        self.window['-STATUS_CONTA-'].update(disabled=False)
                        self.window['-SCAN_ATIVOS-'].update(disabled=False)
                        
                        is_otc = values['-IS_OTC-']
                        temp_selector = AtivoSelector(self.api, self.logger, self.performance)
                        self.todos_ativos = temp_selector.get_todos_ativos_disponiveis(is_otc)
                        self.window['-ATIVO-'].update(values=['AUTO-SCAN'] + self.todos_ativos)
                        
                        self._atualizar_dashboard()
                        self.log(f"Conectado! Conta: {tipo}", 'success')
                        self.log(f"Saldo: {self._format_brl(self.saldo_inicial)}", 'info')
                    else:
                        self.log(f"Falha: {reason}", 'error')
                        
                except Exception as e:
                    self.log(f"Erro: {e}", 'error')

            if event == '-STATUS_CONTA-':
                if self.api:
                    saldo = self.api.get_balance()
                    self.log(f"Saldo Atual: {self._format_brl(saldo)}", 'info')
                    self.log(f"Lucro Sessao: {self._format_brl(self.lucro_sessao)}", 'info')
                    total_trades = self.wins + self.losses
                    if total_trades > 0:
                        self.log(f"Performance: {self.wins}W {self.losses}L ({self.wins/total_trades*100:.1f}%)", 'info')

            if event == '-START-':
                if not self.api:
                    self.log("Conecte-se primeiro!", 'error')
                    continue
                
                self.is_running = True
                self.window['-START-'].update(disabled=True)
                self.window['-STOP-'].update(disabled=False)
                self.window['-STATUS-'].update('OPERANDO')
                self.window['-STATUS-'].update(text_color=self.theme['TITLE_GREEN'])
                
                thread = threading.Thread(target=self.executar_ciclo, args=(values,), daemon=True)
                thread.start()

            if event == '-STOP-':
                self.is_running = False
                self.window['-START-'].update(disabled=False)
                self.window['-STOP-'].update(disabled=True)
                self.window['-STATUS-'].update('PARADO')
                self.window['-STATUS-'].update(text_color=self.theme['TEXT_PRIMARY'])
                self.log("Robo parado.", 'warn')

        if self.logger:
            self.logger.stop()
        self.window.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        handlers=[logging.FileHandler("dashboard.log", encoding='utf-8')]
    )
    
    app = FrancisXDashboard()
    app.run()