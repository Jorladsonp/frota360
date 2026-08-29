# Frota360 · Gestão de Frotas

MVP de gestão de frotas construído com Python, Django Templates, Bootstrap 5, JavaScript e Chart.js. A aplicação separa as experiências de gestor e motorista e mantém os dados isolados por empresa (multi-tenant lógico).

## Destaques

- Dashboard operacional com métricas, alertas prioritários e saúde da frota.
- Financeiro com visões de produção, remuneração, custos fixos, custos por caminhão e resultado estimado.
- Gráficos interativos: clique em uma barra, ponto ou fatia para aplicar o filtro correspondente; o controle **Clique para filtrar** permite desativar essa interação.
- Cores distintas para valores negativos, filtros por período e indicadores de consumo (km/L).
- Barra lateral recolhível, modo escuro e layout responsivo.
- Auditoria ao reabrir trechos concluídos e regras de negócio para odômetro, abastecimentos e remuneração.

## Requisitos

- Python 3.12 ou compatível
- Git

O banco padrão é SQLite; não é necessário instalar um servidor de banco para executar a demonstração.

## Execução local (Windows / PowerShell)

```powershell
git clone https://github.com/Jorladsonp/frota360.git
cd frota360
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo_data
.\.venv\Scripts\python.exe manage.py runserver
```

Abra `http://127.0.0.1:8000/`.

> Não é preciso ativar o ambiente virtual. Usar diretamente `.\.venv\Scripts\python.exe` evita o bloqueio de scripts da política padrão do PowerShell. Se preferir ativá-lo, execute `Set-ExecutionPolicy -Scope Process Bypass` somente no terminal atual e depois `.\.venv\Scripts\Activate.ps1`.

O arquivo [`.vscode/settings.json`](.vscode/settings.json) já seleciona esse interpretador e habilita o uso do `.env` nos terminais do VS Code.

## GitHub Codespaces / Dev Container

Ao abrir o repositório, aceite **Reabrir no Contêiner**. O Dev Container instala as dependências, executa as migrations, copia o `.env.example` e inicia a aplicação na porta `8000` quando o ambiente é conectado.

Se necessário, rode manualmente no terminal Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver 0.0.0.0:8000
```

No Codespaces, abra a porta `8000` pela aba **Ports**.

## Acesso de demonstração

O comando `seed_demo_data` cria somente dados fictícios:

| Perfil | Usuário | Senha |
| --- | --- | --- |
| Gestor | `gestor_demo` | `GestorDemo!2026` |
| Motorista | `motorista1_demo` | `MotoristaDemo!2026` |

Também são criados `motorista2_demo`, `motorista3_demo` e `motorista4_demo`, todos com a senha `MotoristaDemo!2026`.

Essas contas servem apenas para demonstração. Troque as credenciais e a `SECRET_KEY` antes de qualquer uso real.

### Administração Django

O Django Admin está em `http://127.0.0.1:8000/admin/`, mas as contas de demonstração não possuem acesso administrativo. Crie uma conta própria:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Depois acesse `/admin/` com essa conta.

## Dados de demonstração

`python manage.py seed_demo_data` é idempotente: cria ou atualiza uma empresa fictícia, cinco caminhões, quatro motoristas, contratos, seis meses de trechos, abastecimentos com histórico válido de km/L, manutenções, pneus, produção, regras e remunerações, além de um trecho em andamento.

## Regras de negócio principais

- Trechos calculam distância pela diferença entre odômetro final e inicial e duração pelo intervalo entre timestamps.
- Um caminhão e um motorista não podem ter dois trechos em andamento; o odômetro não pode retroceder.
- Trechos finalizados são bloqueados. Um gestor precisa informar o motivo ao reabrir o registro, e a ação fica no `AuditLog`.
- Km/L somente é calculado entre abastecimentos completos e válidos, com quilometragem crescente.
- Comissão usa o valor realizado da produção e a regra vigente mais específica; bônus podem ser por km, viagens, fixo ou percentual.
- O **resultado operacional estimado** subtrai combustível, manutenção, pneus, financiamento, custos fixos e remuneração da receita realizada. Ele não representa lucro contábil.
- O salário fixo é rateado pela distância mensal dos caminhões; na ausência de distância, pela quantidade de viagens.

## Estrutura

- `hello_world/`: configurações, ASGI/WSGI e URLs.
- `fleet/models.py`: entidades operacionais, financeiras, remuneração e auditoria.
- `fleet/services.py`: cálculos de remuneração, custos e rateio.
- `fleet/views.py` e `fleet/forms.py`: fluxos web e validações por perfil.
- `fleet/templates/` e `fleet/static/fleet/`: telas e componentes visuais.
- `fleet/management/commands/seed_demo_data.py`: dados fictícios reproduzíveis.
- `fleet/admin.py`: modelos registrados no Django Admin.
- `fleet/tests.py`: testes de autenticação, isolamento por empresa, operação, gráficos e fórmulas.

## Testes e verificações

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

Para validar a sintaxe do JavaScript, com Node.js instalado:

```powershell
node --check fleet\static\fleet\app.js
```

## Produção e limitações do MVP

O protótipo usa SQLite. Para produção, configure PostgreSQL e revise `ALLOWED_HOSTS`, HTTPS, arquivos de mídia, backups, permissões e as credenciais de demonstração.

Não há GPS/telemetria, aplicativo nativo, integração com postos ou bancos, importação de Excel, manutenção preditiva ou controle avançado de pneus. A produção é lançada manualmente pelo gestor; entradas sem caminhão são rateadas por distância — ou por viagens quando não há distância no período.
