import time
import logging
from iqoptionapi.stable_api import IQ_Option

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IQService:
    def __init__(self, email, password, account_type="PRACTICE"):
        self.email = email
        self.api = IQ_Option(email, password)
        self.account_type = account_type.upper()
        self.connected = False

    def connect(self):
        try:
            logger.info(f"Conectando com email: {self.email[:3]}...")
            check, reason = self.api.connect()
            if check:
                logger.info(f"Conexão OK, mudando para conta: {self.account_type}")
                self.api.change_balance(self.account_type)
                self.connected = True
                return True
            else:
                logger.error(f"Falha na conexão: {reason}")
                return False
        except Exception as e:
            logger.error(f"Erro na conexão: {e}")
            return False

    def get_balance(self):
        try:
            balance = self.api.get_balance()
            logger.debug(f"Saldo obtido: {balance}")
            return balance
        except Exception as e:
            logger.error(f"Erro get_balance: {e}")
            return None

    def get_turbo_assets(self, include_otc=True, include_non_otc=True):
        """Retorna ativos turbo com sufixos corretos"""
        try:
            logger.info(f"Obtendo ativos: OTC={include_otc}, Não-OTC={include_non_otc}")
            all_assets = self.api.get_all_open_time()
            
            if not all_assets:
                logger.warning("API não retornou ativos")
                return self._get_fallback_assets(include_otc, include_non_otc)
            
            opened = []
            
            # Procura em turbo e binary
            for type_name in ['turbo', 'binary']:
                if type_name in all_assets:
                    logger.debug(f"Analisando tipo: {type_name}")
                    type_data = all_assets[type_name]
                    
                    if not isinstance(type_data, dict):
                        logger.warning(f"Dados do tipo {type_name} inválidos")
                        continue
                    
                    for asset_name, data in type_data.items():
                        try:
                            if not isinstance(data, dict):
                                continue
                                
                            # Verifica se está aberto
                            is_open = data.get('open', False) or data.get('enabled', False)
                            
                            if is_open:
                                # Mantém o nome EXATO como a API retorna
                                opened.append(asset_name)
                                logger.debug(f"Ativo {asset_name} - Aberto")
                                
                        except Exception as e:
                            logger.debug(f"Erro processando {asset_name}: {e}")
                            continue
            
            # Filtra conforme solicitado
            filtered_assets = []
            for asset in opened:
                asset_lower = asset.lower()
                
                # Decide se inclui baseado nos parâmetros
                include = False
                
                if '-otc' in asset_lower and include_otc:
                    include = True
                elif '-op' in asset_lower and include_non_otc:
                    include = True
                elif (not '-otc' in asset_lower and not '-op' in asset_lower) and include_non_otc:
                    include = True  # Ativos sem sufixo (raros)
                
                if include:
                    filtered_assets.append(asset)
            
            logger.info(f"Total ativos encontrados: {len(opened)}, filtrados: {len(filtered_assets)}")
            
            if not filtered_assets:
                logger.warning("Nenhum ativo após filtro, usando fallback")
                return self._get_fallback_assets(include_otc, include_non_otc)
            
            # Log dos primeiros ativos para debug
            if filtered_assets:
                logger.info(f"Primeiros 10 ativos: {filtered_assets[:10]}")
            
            return sorted(list(set(filtered_assets)))
            
        except Exception as e:
            logger.error(f"Erro get_turbo_assets: {e}")
            return self._get_fallback_assets(include_otc, include_non_otc)

    def _get_fallback_assets(self, include_otc=True, include_non_otc=True):
        """Lista fallback de ativos"""
        fallback = []
        
        # Ativos não-OTC comuns
        if include_non_otc:
            non_otc = [
                "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
                "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "GBPCHF",
                "EURCHF", "USDCHF", "NZDUSD", "AUDNZD", "GBPNZD",
                "EURNZD", "EURCAD", "AUDCAD", "CADJPY", "CHFJPY"
            ]
            # Adiciona sufixo -op se a API espera
            non_otc = [f"{a}-op" for a in non_otc]
            fallback.extend(non_otc)
        
        # Ativos OTC comuns
        if include_otc:
            otc = [
                "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDUSD-OTC",
                "EURGBP-OTC", "USDCAD-OTC", "NZDUSD-OTC", "USDCHF-OTC"
            ]
            fallback.extend(otc)
        
        logger.warning(f"Usando {len(fallback)} ativos fallback")
        return fallback

    def buy_binary(self, asset, amount, direction, duration):
        """Executa a compra - USA O NOME EXATO DA API"""
        try:
            logger.info(f"BUY: {asset} ${amount} {direction} {duration}min")
            
            # IMPORTANTE: Usa o nome EXATO como a API retornou
            direction = direction.lower()  # "call" ou "put"
            
            # Tenta comprar
            ok, id = self.api.buy(amount, asset, direction, duration)
            
            if ok:
                logger.info(f"✅ Compra OK! ID: {id}")
                return ok, id, None
            else:
                logger.error(f"❌ Compra falhou para {asset}")
                return False, None, f"API retornou false para {asset}"
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"🔥 Erro em buy_binary: {error_msg}")
            return False, None, error_msg

    def check_binary_result(self, order_id, timeout_sec=None):
        """Busca o resultado real"""
        if not order_id:
            logger.error("Order ID inválido")
            return None
        
        try:
            max_wait = timeout_sec if timeout_sec else 90
            start_time = time.time()
            
            logger.info(f"Aguardando resultado para ID: {order_id}")
            
            while time.time() - start_time < max_wait:
                try:
                    # Tenta check_win_v4 primeiro
                    result = self.api.check_win_v4(order_id)
                    
                    if result is not None:
                        win_status, profit_amount = result
                        logger.info(f"Resultado: {win_status}, Valor: {profit_amount}")
                        
                        if win_status == 'win':
                            return float(profit_amount) if profit_amount else 0.0
                        elif win_status == 'equal':
                            return 0.0
                        elif win_status == 'loose':
                            return float(profit_amount) if profit_amount else 0.0
                    
                    time.sleep(2)  # Polling a cada 2s
                    
                except Exception as e:
                    logger.debug(f"Erro durante polling: {e}")
                    time.sleep(2)
            
            # Timeout
            logger.warning(f"⏰ Timeout para order {order_id}")
            return None
            
        except Exception as e:
            logger.error(f"Erro check_binary_result: {e}")
            return None

    def get_candles(self, asset, timeframe, count):
        """Obtém velas históricas"""
        try:
            logger.debug(f"Obtendo candles: {asset}, TF: {timeframe}, Count: {count}")
            return self.api.get_candles(asset, timeframe, count, time.time())
            
        except Exception as e:
            logger.error(f"Erro get_candles ({asset}): {e}")
            return []

    def get_turbo_payout(self, asset):
        """Retorna payout como fração"""
        try:
            # Remove sufixos para lookup
            clean_name = asset
            for suffix in ['-op', '-OTC', '-otc']:
                if clean_name.endswith(suffix):
                    clean_name = clean_name[:-len(suffix)]
                    break
            
            logger.debug(f"Buscando payout para {asset} (clean: {clean_name})")
            
            all_profit = self.api.get_all_profit()
            
            if clean_name in all_profit:
                if 'turbo' in all_profit[clean_name]:
                    payout = all_profit[clean_name]['turbo']
                    logger.debug(f"Payout turbo: {payout}")
                    return payout
                elif 'binary' in all_profit[clean_name]:
                    payout = all_profit[clean_name]['binary']
                    logger.debug(f"Payout binary: {payout}")
                    return payout
            
            # Fallback baseado no tipo
            if '-OTC' in asset or '-otc' in asset:
                logger.debug(f"Payout padrão OTC: 0.84")
                return 0.84
            else:
                logger.debug(f"Payout padrão não-OTC: 0.85")
                return 0.85
                
        except Exception as e:
            logger.error(f"Erro get_turbo_payout ({asset}): {e}")
            return 0.85

    def get_turbo_payout_percent(self, asset):
        """Retorna payout em percentual"""
        try:
            payout = self.get_turbo_payout(asset)
            percent = int(payout * 100)
            logger.debug(f"Payout {asset}: {percent}%")
            return percent
        except Exception as e:
            logger.error(f"Erro get_turbo_payout_percent ({asset}): {e}")
            return 85

    # Métodos de compatibilidade
    def get_payout(self, asset):
        return self.get_turbo_payout_percent(asset)

    def get_binary_payout(self, asset):
        return self.get_turbo_payout_percent(asset)

    def get_payout_percent(self, asset):
        return self.get_turbo_payout_percent(asset)

    def payout(self, asset):
        return self.get_turbo_payout_percent(asset)

    # Métodos para BotEngine
    def is_otc_asset(self, asset):
        """Retorna True se o ativo é OTC"""
        return '-OTC' in asset or '-otc' in asset

    def is_non_otc_asset(self, asset):
        """Retorna True se o ativo é não-OTC (tem -op)"""
        return '-op' in asset

    def get_otc_turbo_assets(self, only_open=True):
        """Retorna apenas ativos OTC"""
        return self.get_turbo_assets(include_otc=True, include_non_otc=False)

    def get_non_otc_turbo_assets(self, only_open=True):
        """Retorna apenas ativos não-OTC"""
        return self.get_turbo_assets(include_otc=False, include_non_otc=True)


    # ===================== MULTI-MERCADO (DIGITAL + BINÁRIA/TURBO) =====================
    def get_all_open(self):
        """Retorna o dicionário completo de mercados abertos (binary/turbo/digital)."""
        try:
            return self.api.get_all_open_time()
        except Exception as e:
            logger.error(f"Erro get_all_open_time: {e}")
            return {}

    def is_open(self, asset: str, market: str) -> bool:
        """
        market: 'digital' | 'turbo' | 'binary'
        Observação: no iqoptionapi, 'turbo' e 'binary' aparecem separados em get_all_open_time().
        """
        try:
            all_open = self.get_all_open()
            md = all_open.get(market, {})
            info = md.get(asset, {})
            return bool(info.get("open", False))
        except Exception:
            return False

    def get_digital_payout_percent(self, asset: str, duration_min: int = 1):
        """
        Tenta obter payout digital (em %) de forma tolerante.
        Dependendo da versão do iqoptionapi, pode existir:
          - get_digital_current_profit(asset, duration_min) -> float (ex 0.92)
        """
        try:
            if hasattr(self.api, "get_digital_current_profit"):
                p = self.api.get_digital_current_profit(asset, duration_min)
                if p is None:
                    return None
                p = float(p)
                # se vier 0.92 => 92%
                if 0 < p <= 2:
                    return round(p * 100.0, 0)
                return round(p, 0)
        except Exception as e:
            logger.debug(f"Digital payout erro: {e}")
        return None

    def buy_digital(self, asset: str, amount: float, direction: str, duration_min: int):
        """
        Compra DIGITAL (spot).
        Retorna: (ok:bool, order_id, err:str|None)
        """
        try:
            direction = direction.lower()
            duration_min = int(duration_min)
            if hasattr(self.api, "buy_digital_spot"):
                ok, order_id = self.api.buy_digital_spot(asset, amount, direction, duration_min)
                if ok:
                    return True, order_id, None
                return False, None, "buy_digital_spot retornou False"
            # fallback: algumas versões usam buy_digital
            if hasattr(self.api, "buy_digital"):
                ok, order_id = self.api.buy_digital(asset, amount, direction, duration_min)
                if ok:
                    return True, order_id, None
                return False, None, "buy_digital retornou False"
            return False, None, "Método digital não disponível na API"
        except Exception as e:
            logger.error(f"🔥 Erro em buy_digital: {e}")
            return False, None, str(e)

    def check_digital_result(self, order_id, timeout_sec: int = 45):
        """
        Espera o resultado DIGITAL. Tolerante a versões:
          - check_win_digital_v2(order_id) -> (bool, profit)
          - check_win_digital(order_id) -> profit
        Retorna profit (float): positivo WIN, negativo LOSS, 0 empate/erro.
        """
        t0 = time.time()
        while time.time() - t0 < max(5, timeout_sec):
            try:
                # v2
                if hasattr(self.api, "check_win_digital_v2"):
                    ok, profit = self.api.check_win_digital_v2(order_id)
                    if ok is True:
                        return float(profit)
                # v1
                if hasattr(self.api, "check_win_digital"):
                    profit = self.api.check_win_digital(order_id)
                    # algumas versões retornam None enquanto não fechou
                    if profit is not None:
                        return float(profit)
            except Exception:
                pass
            time.sleep(1)
        return None

    def buy_best(self, asset: str, amount: float, direction: str, duration_min: int,
                 prefer=("digital", "turbo", "binary")):
        """
        Tenta comprar no melhor mercado disponível:
        - prefer: ordem de preferência.
        Retorna: (ok, order_id, market, err)
        """
        duration_min = int(duration_min)
        direction = direction.lower()

        # Descobre mercados abertos
        all_open = self.get_all_open()
        open_markets = set(k for k in ("digital", "turbo", "binary") if k in all_open)

        for market in prefer:
            if market not in open_markets:
                continue
            # ativo aberto nesse market?
            if not self.is_open(asset, market):
                continue

            # payout mínimo (se conseguir medir)
            if market == "digital":
                p = self.get_digital_payout_percent(asset, duration_min=duration_min)
                if p is not None and p < float(getattr(self, "min_payout", 0) or 0):
                    # se você quiser exigir payout também no digital, deixe assim
                    pass
                ok, oid, err = self.buy_digital(asset, amount, direction, duration_min)
                if ok:
                    return True, oid, "digital", None
            else:
                ok, oid, err = self.buy_binary(asset, amount, direction, duration_min)
                if ok:
                    # 'turbo' e 'binary' usam mesma compra na prática no stable_api
                    return True, oid, market, None

        return False, None, None, "Nenhum mercado disponível para este ativo"

    def check_result(self, order_id, market: str, timeout_sec: int = 45):
        """
        Retorna o profit final para o mercado escolhido.
        """
        market = (market or "").lower()
        if market == "digital":
            return self.check_digital_result(order_id, timeout_sec=timeout_sec)
        # turbo/binary
        return self.check_binary_result(order_id, timeout_sec=timeout_sec)

