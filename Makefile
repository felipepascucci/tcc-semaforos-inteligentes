# Alvos do Bloco 3 — malha, calibração, demanda e execução.
#
# Cada alvo é um atalho para um módulo Python, e não um script à parte. É de
# propósito: no Windows não há `make` por padrão, e a equipe roda os comandos
# `python -m ...` diretamente. O Makefile documenta a ORDEM e as dependências
# entre eles; quem não tiver make lê as receitas e roda à mão.
#
# A ordem importa e não é arbitrária:
#
#     rede -> saturacao -> cenarios -> fluxos -> (executor | validar)
#
# `saturacao` MEDE o fluxo de saturação da malha construída; `cenarios` deriva
# dele o grau de saturação; `fluxos` congela a demanda derivada. Trocar a ordem
# produz uma demanda calculada sobre uma malha que não é a que roda.

PYTHON ?= python
CENARIO ?= leve
MODO ?= FIXO
SEED ?= 1

.PHONY: ajuda rede saturacao cenarios fluxos calibrar validar executar demo teste lint

ajuda:
	@echo "rede        constrói malha.net.xml e os detectores (3.1, 3.2)"
	@echo "saturacao   MEDE o fluxo de saturação na malha (3.0) — exige SUMO"
	@echo "cenarios    deriva o grau de saturação de cada cenário (3.0)"
	@echo "fluxos      regera os fluxo_*.rou.xml a partir da calibração (3.3)"
	@echo "calibrar    saturacao + cenarios + fluxos, na ordem"
	@echo "validar     valida a malha antes de experimentar (3.4)"
	@echo "executar    uma execução (CENARIO=$(CENARIO) MODO=$(MODO) SEED=$(SEED))"
	@echo "demo        a mesma execução na sumo-gui, para ver o corredor verde"
	@echo "lote        a matriz inteira (SEEDS=$(SEEDS) PARALELO=$(PARALELO))"
	@echo "piloto      lote + relatório do Bloco 4"
	@echo "teste       pytest (padrão) + pytest -m sumo"
	@echo "lint        ruff check, ruff format --check e mypy"

# --- 3.1 e 3.2 -------------------------------------------------------------
rede:
	$(PYTHON) -m sim.rede.construir

# --- 3.0 -------------------------------------------------------------------
saturacao: rede
	$(PYTHON) -m sim.calibracao.fluxo_saturacao

cenarios:
	$(PYTHON) -m sim.calibracao.cenarios

fluxos:
	$(PYTHON) -m sim.demanda.gerar_fluxos

calibrar: saturacao cenarios fluxos

# --- 3.4 -------------------------------------------------------------------
validar: rede
	$(PYTHON) -m sim.validacao.malha --cenario $(CENARIO)

# --- 3.7 -------------------------------------------------------------------
executar:
	$(PYTHON) -m sim.controlador.executor --cenario $(CENARIO) --modo $(MODO) --seed $(SEED)

# O primeiro VE entra aos 300 s (o aquecimento de cenarios.yaml), então uma
# demonstração precisa passar disso para ter o que mostrar. 900 s dão dois VEs.
demo:
	$(PYTHON) -m sim.controlador.executor --cenario $(CENARIO) --modo PREEMPCAO \
		--seed $(SEED) --duracao 900 --gui --sem-banco

# --- Bloco 4 (piloto) e Bloco 8 (lote completo) ----------------------------
# O mesmo alvo serve aos dois: o que muda é SEEDS. Com PARALELO=6, as 60
# execuções do piloto levam ~40 min nesta máquina (8 núcleos físicos).
SEEDS ?= 1..5
PARALELO ?= 4

lote:
	$(PYTHON) -m sim.controlador.lote --seeds $(SEEDS) --paralelo $(PARALELO)

# Lê analysis/data/ e escreve docs/relatorios/piloto_AAAAMMDD.md. Nenhum número
# do relatório é digitado à mão (regra de ouro do CLAUDE.md).
relatorio-piloto:
	$(PYTHON) -m analysis.relatorio_piloto

piloto: lote relatorio-piloto

# --- qualidade -------------------------------------------------------------
teste:
	$(PYTHON) -m pytest
	$(PYTHON) -m pytest -m sumo

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m mypy
