import logging
from datetime import datetime
from typing import Dict, Any, Optional
import httpx

import config

logger = logging.getLogger(__name__)

class IddasApiClient:
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or config.IDDAS_API_KEY
        self.base_url = (base_url or config.IDDAS_BASE_URL).rstrip('/')
        self.access_token: Optional[str] = None

    async def authenticate(self) -> str:
        """Autentica na API do IDDAS e armazena o token de acesso Bearer."""
        url = f"{self.base_url}/auth/login"
        payload = {"chave": self.api_key}

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                logger.info("[IDDAS API] Autenticação realizada com sucesso!")
                return self.access_token
            else:
                error_msg = f"Falha na autenticação IDDAS ({response.status_code}): {response.text}"
                logger.error(f"[IDDAS API] {error_msg}")
                raise Exception(error_msg)

    def _get_headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise Exception("Token de acesso IDDAS não disponível. Execute authenticate() primeiro.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def buscar_pessoa_por_cpf_cnpj(self, cpf_cnpj: str) -> Optional[int]:
        """Busca se a pessoa (cliente ou fornecedor) já existe no IDDAS por CPF/CNPJ."""
        if not cpf_cnpj:
            return None

        url = f"{self.base_url}/pessoa"
        params = {"cpf_cnpj": cpf_cnpj}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=self._get_headers(), params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    # Se data for lista ou dict contendo data
                    items = data if isinstance(data, list) else data.get("data", [])
                    if isinstance(items, list) and len(items) > 0:
                        return items[0].get("id")
        except Exception as e:
            logger.warning(f"[IDDAS API] Erro ao buscar pessoa por CPF/CNPJ: {e}")

        return None

    async def cadastrar_cliente(self, cliente_data: Dict[str, Any]) -> int:
        """Cadastra ou reutiliza um Cliente (Pessoa) no IDDAS."""
        cpf = cliente_data.get("cpf", "")
        existing_id = await self.buscar_pessoa_por_cpf_cnpj(cpf)
        if existing_id:
            logger.info(f"[IDDAS API] Cliente CPF {cpf} já existe com ID {existing_id}")
            return existing_id

        url = f"{self.base_url}/pessoa"
        payload = {
            "tipo_cliente": "S",
            "tipo_passageiro": "S",
            "tipo_fornecedor": "N",
            "nome": cliente_data.get("nome", "Cliente Sem Nome"),
            "cpf_cnpj": cpf,
            "nascimento": cliente_data.get("data_nascimento") or None,
            "email": cliente_data.get("email") or None,
            "celular": cliente_data.get("telefone") or None,
            "aceita_comunicacao": "S"
        }
        # Remove valores None do payload
        payload = {k: v for k, v in payload.items() if v is not None}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=self._get_headers(), json=payload)
            if resp.status_code in (200, 201):
                res_json = resp.json()
                pessoa_id = res_json.get("data", {}).get("id") or res_json.get("id")
                logger.info(f"[IDDAS API] Cliente cadastrado com sucesso! ID: {pessoa_id}")
                return pessoa_id
            else:
                raise Exception(f"Erro ao cadastrar cliente no IDDAS ({resp.status_code}): {resp.text}")

    async def cadastrar_fornecedor(self, fornecedor_data: Dict[str, Any]) -> int:
        """Cadastra ou reutiliza um Fornecedor (Pessoa) no IDDAS."""
        cpf_cnpj = fornecedor_data.get("cpf_cnpj", "")
        existing_id = await self.buscar_pessoa_por_cpf_cnpj(cpf_cnpj)
        if existing_id:
            logger.info(f"[IDDAS API] Fornecedor {cpf_cnpj} já existe com ID {existing_id}")
            return existing_id

        url = f"{self.base_url}/pessoa"
        payload = {
            "tipo_cliente": "N",
            "tipo_passageiro": "N",
            "tipo_fornecedor": "S",
            "nome": fornecedor_data.get("nome", "Fornecedor Sem Nome"),
            "cpf_cnpj": cpf_cnpj,
            "celular": fornecedor_data.get("telefone") or None
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=self._get_headers(), json=payload)
            if resp.status_code in (200, 201):
                res_json = resp.json()
                fornecedor_id = res_json.get("data", {}).get("id") or res_json.get("id")
                logger.info(f"[IDDAS API] Fornecedor cadastrado com sucesso! ID: {fornecedor_id}")
                return fornecedor_id
            else:
                raise Exception(f"Erro ao cadastrar fornecedor no IDDAS ({resp.status_code}): {resp.text}")

    async def criar_orcamento(self, cliente_id: int, titulo: str) -> int:
        """Cria o orçamento/venda vinculada ao Cliente."""
        url = f"{self.base_url}/orcamento"
        today = datetime.now().strftime("%Y-%m-%d")

        payload = {
            "cliente": str(cliente_id),
            "canal_venda": str(config.DEFAULT_CANAL_VENDA_ID),
            "situacao": "E",
            "titulo": titulo,
            "passageiros_adulto": 1,
            "passageiros_crianca": 0,
            "passageiros_bebe": 0,
            "idPassageiros": [cliente_id],
            "data_orcamento": today
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=self._get_headers(), json=payload)
            if resp.status_code in (200, 201):
                res_json = resp.json()
                orcamento_id = res_json.get("data", {}).get("id") or res_json.get("id")
                logger.info(f"[IDDAS API] Orçamento/Venda criada com sucesso! ID: {orcamento_id}")
                return int(orcamento_id)
            else:
                raise Exception(f"Erro ao criar orçamento no IDDAS ({resp.status_code}): {resp.text}")

    async def cadastrar_voo(self, orcamento_id: int, voo_data: Dict[str, Any]) -> int:
        """Cadastra um voo vinculado ao Orçamento/Venda."""
        url = f"{self.base_url}/voo"

        today = datetime.now().strftime("%Y-%m-%d")

        payload = {
            "id_orcamento": orcamento_id,
            "tipo_trecho": voo_data.get("tipo_trecho", "I"),
            "voo": voo_data.get("voo", "VOO 0000"),
            "aeroporto_origem": voo_data.get("aeroporto_origem", "GRU"),
            "aeroporto_destino": voo_data.get("aeroporto_destino", "GIG"),
            "data_embarque": voo_data.get("data_embarque") or today,
            "hora_embarque": voo_data.get("hora_embarque", "08:00:00"),
            "data_chegada": voo_data.get("data_chegada") or today,
            "hora_chegada": voo_data.get("hora_chegada", "10:00:00"),
            "localizador": voo_data.get("localizador", ""),
            "checkin": "1"
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=self._get_headers(), json=payload)
            if resp.status_code in (200, 201):
                res_json = resp.json()
                voo_id = res_json.get("data", {}).get("id") or res_json.get("id")
                logger.info(f"[IDDAS API] Voo {payload['voo']} cadastrado com sucesso! ID: {voo_id}")
                return int(voo_id) if voo_id else 0
            else:
                logger.error(f"[IDDAS API] Erro ao cadastrar voo: {resp.text}")
                return 0

    async def lançar_receita(self, cliente_id: int, valor: float, localizador: str) -> Optional[int]:
        """Lança o valor da VENDA no módulo financeiro (Receita)."""
        if valor <= 0:
            return None

        url = f"{self.base_url}/receita"
        today = datetime.now().strftime("%Y-%m-%d")

        payload = {
            "pessoa": cliente_id,
            "conta": config.DEFAULT_CONTA_ID,
            "categoria": config.DEFAULT_CATEGORIA_RECEITA_ID,
            "descricao": f"Venda Bilhete Aéreo {localizador}".strip(),
            "lancamento": today,
            "vencimento": today,
            "forma_lancamento": "N",
            "forma_pagamento": config.DEFAULT_FORMA_PAGAMENTO_ID,
            "valor": valor,
            "parcela": 1
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=self._get_headers(), json=payload)
            if resp.status_code in (200, 201):
                res_json = resp.json()
                rec_id = res_json.get("data", {}).get("id") or res_json.get("id")
                logger.info(f"[IDDAS API] Receita R$ {valor:.2f} lançada com sucesso! ID: {rec_id}")
                return int(rec_id) if rec_id else None
            else:
                logger.error(f"[IDDAS API] Erro ao lançar receita: {resp.text}")
                return None

    async def lançar_despesa(self, fornecedor_id: int, valor: float, localizador: str) -> Optional[int]:
        """Lança o valor de CUSTO no módulo financeiro (Despesa)."""
        if valor <= 0:
            return None

        url = f"{self.base_url}/despesa"
        today = datetime.now().strftime("%Y-%m-%d")

        payload = {
            "pessoa": fornecedor_id,
            "conta": config.DEFAULT_CONTA_ID,
            "categoria": config.DEFAULT_CATEGORIA_DESPESA_ID,
            "descricao": f"Custo Emissão Bilhete {localizador}".strip(),
            "lancamento": today,
            "vencimento": today,
            "forma_lancamento": "N",
            "forma_pagamento": config.DEFAULT_FORMA_PAGAMENTO_ID,
            "valor": valor,
            "parcela": 1
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=self._get_headers(), json=payload)
            if resp.status_code in (200, 201):
                res_json = resp.json()
                desp_id = res_json.get("data", {}).get("id") or res_json.get("id")
                logger.info(f"[IDDAS API] Despesa R$ {valor:.2f} lançada com sucesso! ID: {desp_id}")
                return int(desp_id) if desp_id else None
            else:
                logger.error(f"[IDDAS API] Erro ao lançar despesa: {resp.text}")
                return None
