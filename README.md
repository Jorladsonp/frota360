# Frota360 · Gestão de Frotas

MVP demonstrável de gestão de frotas construído com Python, Django Templates, Bootstrap 5, JavaScript e Chart.js. A aplicação tem experiências separadas para gestor e motorista e está preparada para isolamento por empresa (multi-tenant lógico).

## Rodando no GitHub Codespaces

O dev container encaminha a porta `8000` e inicia o servidor no endereço acessível pelo Codespaces. Manualmente:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver 0.0.0.0:8000
```

Abra a porta 8000 na aba **Ports** do Codespaces. O comando também funciona localmente com `http://127.0.0.1:8000/`.

## Credenciais fictícias

O seed cria usuários separados, sem documentos ou dados pessoais reais:

- Gestor: `gestor_demo` / `GestorDemo!2026`
- Motorista: `motorista1_demo` / `MotoristaDemo!2026`
- Outros motoristas: `motorista2_demo`, `motorista3_demo`, `motorista4_demo`, com a mesma senha `MotoristaDemo!2026`

Essas credenciais são apenas para a demonstração. Em ambiente real, troque-as e configure uma `SECRET_KEY` própria no `.env`.

## Dados demo

`python manage.py seed_demo_data` é idempotente: cria ou atualiza uma empresa fictícia, 5 caminhões (3 financiados e 2 quitados), 4 motoristas, 3 contratos, seis meses de trechos, abastecimentos, manutenções, pneus, produção, regras de remuneração e remunerações históricas, além de um trecho em andamento.

## Regras de negócio principais

- Trechos calculam distância pela diferença entre odômetro final e inicial e duração pelo intervalo entre os timestamps.
- Um caminhão e um motorista não podem ter dois trechos em andamento. O odômetro não pode retroceder.
- Trechos finalizados são bloqueados no modelo e na interface. Um gestor precisa reabrir o registro com motivo; a ação e o antes/depois ficam em `AuditLog`.
- Preço por litro é `valor total / litros`.
- Km/L somente é calculado quando o abastecimento atual e o anterior são tanques completos válidos, com quilometragem crescente.
- Comissão utiliza o valor realizado da produção. A regra aplicada é a vigente, mais específica e com maior prioridade; bônus podem ser por km, viagens, fixo ou percentual.
- Resultado sempre aparece como **Resultado operacional estimado**, nunca como lucro contábil. Ele subtrai combustível, manutenção, pneus, financiamento, custos fixos e remuneração da receita realizada.
- Salário fixo do motorista é rateado por distância dos caminhões no mês; se não houver distância, usa-se quantidade de viagens.
- Todos os registros principais têm `company` e as telas filtram por empresa. Um motorista só consulta os próprios trechos, abastecimentos, ocorrências e remuneração.

## Estrutura

- `hello_world/`: configurações, ASGI/WSGI e URLs do projeto.
- `fleet/models.py`: entidades da operação, financeiro, remuneração e auditoria.
- `fleet/services.py`: cálculos de remuneração, custos e rateio.
- `fleet/views.py`, `fleet/forms.py`: fluxos web e validações por perfil.
- `fleet/templates/` e `fleet/static/fleet/`: interface responsiva do gestor e painel mobile-first do motorista.
- `fleet/management/commands/seed_demo_data.py`: dados fictícios reproduzíveis.
- `fleet/admin.py`: todos os modelos principais registrados no Django Admin.
- `fleet/tests.py`: testes de autenticação, tenant, operação e fórmulas.

## Testes e verificações

```bash
python manage.py check
python manage.py test
```

## PostgreSQL no futuro

O protótipo usa SQLite por padrão. As configurações sensíveis já são lidas do ambiente com `python-decouple`, e o `.env.example` reserva as variáveis para PostgreSQL. Para uma implantação real, basta configurar o backend/URL do banco, executar as migrations e revisar `ALLOWED_HOSTS`, HTTPS, arquivos de mídia e política de backups.

## Limitações intencionais do MVP

Não há GPS/telemetria, app nativo, integração com postos ou bancos, importação de Excel, busca externa de preços, fórmulas livres, manutenção preditiva, controle individual avançado de pneus, troca de caminhão durante um trecho ou múltiplos motoristas no mesmo trecho. A produção é lançada manualmente pelo gestor; entradas de contrato/competência sem caminhão são rateadas por distância (ou viagens) no período.

## Próximas evoluções

Permissões mais granulares, paginação e filtros avançados, PostgreSQL, anexos com storage dedicado, rateio formal de produção mensal, fechamento/aprovação com trilha completa, API para telemetria, notificações e controle de vida útil/posição de pneus.
