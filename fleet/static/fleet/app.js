function initAppChrome() {
  if (document.documentElement.dataset.appChromeInitialized) return;
  document.documentElement.dataset.appChromeInitialized = 'true';
  const appShell = document.querySelector('.app-shell');
  const sidebar = document.getElementById('mainSidebar');
  const mobileToggle = document.querySelector('[data-sidebar-toggle]');
  if (mobileToggle && sidebar) mobileToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
  if (appShell && sidebar) {
    const collapseButtons = document.querySelectorAll('[data-sidebar-collapse]');
    let collapsed = false;
    try { collapsed = window.localStorage.getItem('frota360:sidebar') === 'collapsed'; } catch (error) { /* menu aberto por padrão */ }
    const setCollapsed = next => {
      appShell.classList.toggle('sidebar-collapsed', next);
      collapseButtons.forEach(button => {
        button.setAttribute('aria-label', next ? 'Abrir menu' : 'Recolher menu');
        button.title = next ? 'Abrir menu' : 'Recolher menu';
      });
    };
    setCollapsed(collapsed);
    collapseButtons.forEach(button => button.addEventListener('click', () => {
      const next = !appShell.classList.contains('sidebar-collapsed');
      setCollapsed(next);
      try { window.localStorage.setItem('frota360:sidebar', next ? 'collapsed' : 'expanded'); } catch (error) { /* memória visual apenas */ }
    }));
  }
  const topbar = document.querySelector('.topbar');
  const userMenu = document.querySelector('.user-menu');
  const topbarActions = document.querySelector('.topbar-actions') || topbar;
  if (topbar && userMenu && !document.querySelector('[data-theme-toggle]')) {
    const theme = document.createElement('button');
    theme.type = 'button';
    theme.className = 'theme-toggle';
    theme.setAttribute('data-theme-toggle', '');
    theme.innerHTML = '<i class="bi bi-moon-stars"></i><span data-theme-label>Modo escuro</span>';
    topbarActions.insertBefore(theme, userMenu);
    const applyTheme = dark => {
      document.documentElement.dataset.theme = dark ? 'dark' : 'light';
      const themeColor = document.querySelector('[data-theme-color]');
      if (themeColor) themeColor.setAttribute('content', dark ? '#111827' : '#3867f4');
      theme.setAttribute('aria-pressed', String(dark));
      theme.querySelector('i').className = dark ? 'bi bi-sun' : 'bi bi-moon-stars';
      theme.querySelector('[data-theme-label]').textContent = dark ? 'Modo claro' : 'Modo escuro';
      if (window.Chart) { Chart.defaults.color = dark ? '#c7d2e5' : '#718096'; Chart.defaults.borderColor = dark ? '#30415d' : '#e7ebf2'; }
    };
    let dark = false;
    try { dark = window.localStorage.getItem('frota360:theme') === 'dark'; } catch (error) { /* tema claro por padrão */ }
    applyTheme(dark);
    theme.addEventListener('click', () => {
      dark = !dark;
      try { window.localStorage.setItem('frota360:theme', dark ? 'dark' : 'light'); } catch (error) { /* sessão atual */ }
      applyTheme(dark);
      window.location.reload();
    });
  }
}

initAppChrome();
document.addEventListener('DOMContentLoaded', initAppChrome);

function registerPwa() {
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  navigator.serviceWorker.register('/service-worker.js').then(registration => registration.update()).catch(error => {
    console.info('PWA indisponível neste ambiente:', error);
  });
}

window.addEventListener('load', registerPwa);

function initDriverDrafts() {
  if (!document.body.classList.contains('driver-app')) return;
  const content = document.querySelector('.page-content');
  const noticeId = 'driver-connection-notice';
  const updateConnection = () => {
    let notice = document.getElementById(noticeId);
    if (!content) return;
    if (!navigator.onLine) {
      if (!notice) {
        notice = document.createElement('div');
        notice.id = noticeId;
        notice.className = 'driver-connection-notice';
        content.prepend(notice);
      }
      notice.innerHTML = '<i class="bi bi-wifi-off"></i><span>Você está sem conexão. Seus campos ficam salvos neste aparelho até a conexão voltar.</span>';
    } else if (notice) notice.remove();
  };
  updateConnection();
  window.addEventListener('online', updateConnection);
  window.addEventListener('offline', updateConnection);
  document.querySelectorAll('form[data-offline-draft]').forEach(form => {
    const key = `frota360:draft:${window.location.pathname}`;
    let saved = {};
    try { saved = JSON.parse(window.localStorage.getItem(key) || '{}'); } catch (error) { saved = {}; }
    form.querySelectorAll('input,select,textarea').forEach(field => {
      if (!field.name || field.type === 'file' || field.type === 'hidden') return;
      if (Object.hasOwn(saved, field.name)) {
        if (field.type === 'checkbox') field.checked = Boolean(saved[field.name]);
        else if (!field.value) field.value = saved[field.name];
      }
      field.addEventListener('input', () => {
        const draft = {};
        form.querySelectorAll('input,select,textarea').forEach(item => {
          if (!item.name || item.type === 'file' || item.type === 'hidden') return;
          draft[item.name] = item.type === 'checkbox' ? item.checked : item.value;
        });
        try { window.localStorage.setItem(key, JSON.stringify(draft)); } catch (error) { /* sem armazenamento disponível */ }
      });
    });
    form.addEventListener('submit', () => { try { window.localStorage.removeItem(key); } catch (error) { /* rascunho expira na próxima gravação */ } });
  });
}

window.addEventListener('DOMContentLoaded', initDriverDrafts);

function fleetCharts(data, operating, maintenance, inactive, breakdown = {}) {
  const chartFont = {family: 'DM Sans'};
  const revenueCanvas = document.getElementById('revenueChart');
  if (revenueCanvas && window.Chart) {
    revenueCanvas.dataset.financialChart = 'true';
    revenueCanvas.style.cursor = financialInteractionsEnabled() ? 'pointer' : 'default';
    new Chart(revenueCanvas, {type:'line', data:{labels:data.labels,datasets:[{label:'Receita',data:data.revenue,borderColor:'#3867f4',backgroundColor:'rgba(56,103,244,.1)',fill:true,tension:.35,pointRadius:3},{label:'Custos',data:data.costs,borderColor:'#ec8b39',backgroundColor:'rgba(236,139,57,.04)',fill:true,tension:.35,pointRadius:3}]},options:{responsive:true,maintainAspectRatio:false,onClick:financialDrilldown((data.starts || []).map((start, index) => ({start, end:data.ends[index]}))),plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:financialChartGrid()},ticks:{font:chartFont,callback:v=>'R$ '+Number(v).toLocaleString('pt-BR')}},x:{grid:{display:false},ticks:{font:chartFont}}}}});
  }
  const fleetCanvas = document.getElementById('fleetChart');
  if (fleetCanvas && window.Chart) financialDoughnut('fleetChart', ['Em operação','Em manutenção','Inativos'], [operating, maintenance, inactive], ['#149b76','#ec8b39','#9aa7ba'], [{fleet_status:'OPERATING'},{fleet_status:'MAINTENANCE'},{fleet_status:'INACTIVE'}], false, false);
  financialBar('resultTruckChart', breakdown.truck_labels, breakdown.result_values, '#149b76', (breakdown.truck_ids || []).map(id => ({truck:id})), true, (breakdown.truck_labels || []).length > 5);
  financialBar('consumptionChart', breakdown.truck_labels, breakdown.km_l_values, '#149b76', (breakdown.truck_ids || []).map(id => ({truck:id})), false, (breakdown.truck_labels || []).length > 5);
  financialBar('maintenanceChart', breakdown.truck_labels, breakdown.maintenance_values, '#df5b66', (breakdown.truck_ids || []).map(id => ({truck:id})), true, (breakdown.truck_labels || []).length > 5);
  financialBar('productionChart', breakdown.contract_labels, breakdown.production_values, '#7b61d8', (breakdown.contract_ids || []).map(id => ({contract:id})), true, (breakdown.contract_labels || []).length > 5);
  financialBar('remunerationChart', breakdown.driver_labels, breakdown.remuneration_values, '#ec8b39', (breakdown.driver_ids || []).map(id => ({driver:id})), true, (breakdown.driver_labels || []).length > 5);
}

function costReportCharts(composition, trucks) {
  if (!window.Chart) return;
  const font = {family: 'DM Sans'};
  const compositionCanvas = document.getElementById('costCompositionChart');
  if (compositionCanvas) financialBar('costCompositionChart', composition.labels, composition.values, ['#3867f4','#df5b66','#ec8b39','#7b61d8','#9bb5ff','#149b76'], (composition.keys || []).map(key => ({component:key})), true, false);
  const trucksCanvas = document.getElementById('truckCostChart');
  if (trucksCanvas) financialBar('truckCostChart', trucks.labels, trucks.values, '#3867f4', (trucks.ids || []).map(id => ({truck:id})), true, (trucks.labels || []).length > 5);
}

function resultReportCharts(comparison, monthly) {
  if (!window.Chart) return;
  const font = {family: 'DM Sans'};
  const money = value => 'R$ '+Number(value).toLocaleString('pt-BR',{minimumFractionDigits:2});
  const comparisonCanvas = document.getElementById('resultComparisonChart');
  if (comparisonCanvas) {
    const comparisonFilters = (comparison.ids || []).map(id => ({truck:id}));
    comparisonCanvas.dataset.financialChart = 'true';
    comparisonCanvas.style.cursor = financialInteractionsEnabled() ? 'pointer' : 'default';
    new Chart(comparisonCanvas, {type:'bar', data:{labels:comparison.labels,datasets:[{label:'Receita',data:comparison.revenue,backgroundColor:comparison.revenue.map(value => Number(value) < 0 ? '#df5b66' : '#3867f4'),borderRadius:5},{label:'Custos',data:comparison.cost,backgroundColor:comparison.cost.map(value => Number(value) < 0 ? '#df5b66' : '#ec8b39'),borderRadius:5},{label:'Resultado',data:comparison.result,backgroundColor:comparison.result.map(value => Number(value) < 0 ? '#df5b66' : '#149b76'),borderRadius:5}]}, options:{responsive:true,maintainAspectRatio:false,onClick:financialDrilldown(comparisonFilters),plugins:{legend:{position:'bottom',labels:{font}},tooltip:{callbacks:{label:ctx=>ctx.dataset.label+': '+money(ctx.raw)}}},scales:{y:{beginAtZero:true,grid:{color:financialChartGrid()},ticks:{font,callback:v=>'R$ '+Number(v).toLocaleString('pt-BR')}},x:{grid:{display:false},ticks:{font}}}}});
  }
  const monthlyCanvas = document.getElementById('monthlyResultChart');
  if (monthlyCanvas) {
    monthlyCanvas.dataset.financialChart = 'true';
    monthlyCanvas.style.cursor = financialInteractionsEnabled() ? 'pointer' : 'default';
    new Chart(monthlyCanvas, {type:'line', data:{labels:monthly.labels,datasets:[{label:'Receita',data:monthly.revenue,borderColor:'#3867f4',backgroundColor:'rgba(56,103,244,.09)',fill:true,tension:.35,pointRadius:3},{label:'Custos',data:monthly.costs,borderColor:'#ec8b39',backgroundColor:'rgba(236,139,57,.05)',fill:true,tension:.35,pointRadius:3},{label:'Resultado',data:monthly.result,borderColor:'#149b76',backgroundColor:'transparent',pointBackgroundColor:monthly.result.map(value => Number(value) < 0 ? '#df5b66' : '#149b76'),tension:.35,pointRadius:3}]}, options:{responsive:true,maintainAspectRatio:false,onClick:financialDrilldown((monthly.starts || []).map((start, index) => ({start, end:monthly.ends[index]}))),plugins:{legend:{position:'bottom',labels:{font}},tooltip:{callbacks:{label:ctx=>ctx.dataset.label+': '+money(ctx.raw)}}},scales:{y:{grid:{color:financialChartGrid()},ticks:{font,callback:v=>'R$ '+Number(v).toLocaleString('pt-BR')}},x:{grid:{display:false},ticks:{font}}}}});
  }
}

function financialMoney(value) {
  return 'R$ ' + Number(value || 0).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function financialChartGrid() {
  return document.documentElement.dataset.theme === 'dark' ? '#30415d' : '#eef1f5';
}

function financialBarColors(values, color) {
  if (Array.isArray(color)) return (values || []).map((value, index) => Number(value) < 0 ? '#df5b66' : color[index] || color[0]);
  return (values || []).map(value => Number(value) < 0 ? '#df5b66' : color);
}

const financialInteractionStorageKey = 'frota360:financial-interactions';

function financialInteractionsEnabled() {
  try {
    return window.localStorage.getItem(financialInteractionStorageKey) !== 'off';
  } catch (error) {
    return true;
  }
}

function updateFinancialInteractionControls() {
  const enabled = financialInteractionsEnabled();
  document.querySelectorAll('[data-financial-toggle]').forEach(toggle => {
    toggle.classList.toggle('is-active', enabled);
    toggle.setAttribute('aria-pressed', String(enabled));
    const state = toggle.querySelector('[data-toggle-state]');
    if (state) state.textContent = enabled ? 'Ativo' : 'Inativo';
  });
  document.querySelectorAll('[data-financial-chart]').forEach(canvas => {
    canvas.style.cursor = enabled ? 'pointer' : 'default';
  });
}

function initFinancialInteractionControls() {
  document.querySelectorAll('[data-financial-toggle]').forEach(toggle => {
    toggle.addEventListener('click', () => {
      try {
        window.localStorage.setItem(financialInteractionStorageKey, financialInteractionsEnabled() ? 'off' : 'on');
      } catch (error) {
        // O comportamento padrão continua ativo quando o navegador bloqueia o storage.
      }
      updateFinancialInteractionControls();
    });
  });
  updateFinancialInteractionControls();
}

let financialPageUpdating = false;

async function refreshFinancialPage(url, updateHistory = true) {
  if (financialPageUpdating) return;
  const content = document.querySelector('.page-content');
  if (!content) {
    window.location.assign(url.toString());
    return;
  }
  financialPageUpdating = true;
  const scrollPosition = window.scrollY;
  content.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch(url.toString(), {headers: {'X-Requested-With': 'XMLHttpRequest'}});
    if (!response.ok) throw new Error(`Falha ao atualizar o filtro: ${response.status}`);
    const markup = await response.text();
    const nextDocument = new DOMParser().parseFromString(markup, 'text/html');
    const nextContent = nextDocument.querySelector('.page-content');
    if (!nextContent) throw new Error('A resposta não contém o conteúdo da página.');
    if (window.Chart && window.Chart.getChart) {
      document.querySelectorAll('canvas').forEach(canvas => {
        const chart = window.Chart.getChart(canvas);
        if (chart) chart.destroy();
      });
    }
    content.replaceChildren(...Array.from(nextContent.childNodes, node => document.importNode(node, true)));
    if (updateHistory) window.history.pushState({financialFilter: true}, '', url.toString());
    nextDocument.querySelectorAll('script:not([src])').forEach(script => {
      if (script.textContent.trim()) new Function(script.textContent)();
    });
    initFinancialInteractionControls();
    initAsyncFilters();
    window.scrollTo(0, scrollPosition);
  } catch (error) {
    console.error(error);
    window.location.assign(url.toString());
  } finally {
    content.removeAttribute('aria-busy');
    financialPageUpdating = false;
  }
}

window.addEventListener('popstate', () => {
  if (document.querySelector('canvas[data-financial-chart]')) refreshFinancialPage(new URL(window.location.href), false);
});

function financialDrilldown(filterSets) {
  return function(event, elements) {
    if (!financialInteractionsEnabled()) return;
    const element = elements && elements[0];
    if (!element || !filterSets[element.index]) return;
    const filters = filterSets[element.index];
    const url = new URL(window.location.href);
    const isSelected = Object.entries(filters).every(([key, value]) => url.searchParams.get(key) === String(value));
    Object.entries(filters).forEach(([key, value]) => isSelected ? url.searchParams.delete(key) : url.searchParams.set(key, value));
    url.searchParams.delete('page');
    refreshFinancialPage(url);
  };
}

function initAsyncFilters() {
  document.querySelectorAll('form[data-async-filter]').forEach(form => {
    if (form.dataset.asyncFilterInitialized) return;
    form.dataset.asyncFilterInitialized = 'true';
    form.addEventListener('submit', event => {
      event.preventDefault();
      const url = new URL(form.action || window.location.href, window.location.origin);
      url.search = '';
      new FormData(form).forEach((value, key) => {
        if (String(value).trim()) url.searchParams.set(key, value);
      });
      refreshFinancialPage(url);
    });
  });
}

function financialScales(money = true) {
  return {x:{grid:{display:false},ticks:{font:{family:'DM Sans'}}},y:{beginAtZero:true,grid:{color:financialChartGrid()},ticks:{font:{family:'DM Sans'},callback:value => money ? financialMoney(value) : Number(value).toLocaleString('pt-BR')}}};
}

function financialBar(id, labels, values, color, filterSets, money = true, horizontal = false) {
  const canvas = document.getElementById(id);
  if (!canvas || !window.Chart) return;
  canvas.dataset.financialChart = 'true';
  canvas.style.cursor = financialInteractionsEnabled() ? 'pointer' : 'default';
  new Chart(canvas, {type:'bar', data:{labels:labels || [], datasets:[{data:values || [],backgroundColor:financialBarColors(values, color),borderRadius:7,borderSkipped:false,barThickness:horizontal ? 22 : undefined}]}, options:{responsive:true,maintainAspectRatio:false,indexAxis:horizontal ? 'y' : 'x',onClick:financialDrilldown(filterSets || []),plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx => money ? financialMoney(ctx.raw) : Number(ctx.raw).toLocaleString('pt-BR')}}},scales:financialScales(money)}});
}

function financialDoughnut(id, labels, values, colors, filterSets, money = true, showLegend = true) {
  const canvas = document.getElementById(id);
  if (!canvas || !window.Chart) return;
  canvas.dataset.financialChart = 'true';
  canvas.style.cursor = financialInteractionsEnabled() ? 'pointer' : 'default';
  new Chart(canvas, {type:'doughnut',data:{labels:labels || [],datasets:[{data:values || [],backgroundColor:colors,borderWidth:0,hoverOffset:6}]},options:{responsive:true,maintainAspectRatio:false,cutout:'68%',onClick:financialDrilldown(filterSets || []),plugins:{legend:showLegend ? {position:'bottom',labels:{font:{family:'DM Sans'},padding:14}} : {display:false},tooltip:{callbacks:{label:ctx => `${ctx.label}: ${money ? financialMoney(ctx.raw) : Number(ctx.raw).toLocaleString('pt-BR')}`}}}}});
}

function productionCharts(monthly, status, contracts) {
  if (!window.Chart) return;
  financialBar('productionMonthlyChart', monthly.labels, monthly.values, '#3867f4', (monthly.starts || []).map((start, index) => ({start, end:monthly.ends[index]})), true, false);
  financialDoughnut('productionStatusChart', status.labels, status.values, ['#3867f4','#149b76','#ec8b39','#df5b66'], (status.keys || []).map(key => ({status:key})));
  financialBar('productionContractChart', contracts.labels, contracts.values, '#7b61d8', (contracts.ids || []).map(id => ({contract:id})), true, (contracts.labels || []).length > 5);
}

function fixedCostCharts(categories, trucks) {
  if (!window.Chart) return;
  financialDoughnut('fixedCategoryChart', categories.labels, categories.values, ['#3867f4','#ec8b39','#7b61d8'], (categories.keys || []).map(key => ({category:key})));
  financialBar('fixedTruckChart', trucks.labels, trucks.values, '#ec8b39', (trucks.ids || []).map(id => ({truck:id})), true, (trucks.labels || []).length > 5);
}

function remunerationCharts(history, drivers) {
  if (!window.Chart) return;
  const historyCanvas = document.getElementById('remunerationHistoryChart');
  if (historyCanvas) {
    historyCanvas.dataset.financialChart = 'true';
    historyCanvas.style.cursor = financialInteractionsEnabled() ? 'pointer' : 'default';
    new Chart(historyCanvas, {type:'line',data:{labels:history.map(item => item.label),datasets:[{label:'Total',data:history.map(item => item.total),borderColor:'#3867f4',backgroundColor:'rgba(56,103,244,.10)',fill:true,tension:.35,pointRadius:3},{label:'Fixo',data:history.map(item => item.fixed),borderColor:'#149b76',tension:.35,pointRadius:2},{label:'Comissão',data:history.map(item => item.commission),borderColor:'#7b61d8',tension:.35,pointRadius:2},{label:'Bônus',data:history.map(item => item.bonus),borderColor:'#ec8b39',tension:.35,pointRadius:2}]},options:{responsive:true,maintainAspectRatio:false,onClick:financialDrilldown(history.map(item => ({competence:item.competence}))),plugins:{legend:{position:'bottom',labels:{font:{family:'DM Sans'}}},tooltip:{callbacks:{label:ctx => `${ctx.dataset.label}: ${financialMoney(ctx.raw)}`}}},scales:financialScales(true)}});
  }
  financialBar('remunerationDriverChart', drivers.labels, drivers.total, '#3867f4', (drivers.ids || []).map(id => ({driver:id})), true, (drivers.labels || []).length > 5);
  const compositionCanvas = document.getElementById('remunerationCompositionChart');
  if (compositionCanvas) {
    compositionCanvas.dataset.financialChart = 'true';
    compositionCanvas.style.cursor = financialInteractionsEnabled() ? 'pointer' : 'default';
    new Chart(compositionCanvas, {type:'bar',data:{labels:drivers.labels || [],datasets:[{label:'Fixo',data:drivers.fixed || [],backgroundColor:'#149b76',borderRadius:5},{label:'Comissão',data:drivers.commission || [],backgroundColor:'#7b61d8',borderRadius:5},{label:'Bônus',data:drivers.bonus || [],backgroundColor:'#ec8b39',borderRadius:5}]},options:{responsive:true,maintainAspectRatio:false,onClick:financialDrilldown((drivers.ids || []).map(id => ({driver:id}))),plugins:{legend:{position:'bottom',labels:{font:{family:'DM Sans'}}},tooltip:{callbacks:{label:ctx => `${ctx.dataset.label}: ${financialMoney(ctx.raw)}`}}},scales:{x:{stacked:true,grid:{display:false},ticks:{font:{family:'DM Sans'}}},y:{stacked:true,beginAtZero:true,grid:{color:financialChartGrid()},ticks:{font:{family:'DM Sans'},callback:financialMoney}}}}});
  }
}

function operationCharts(data) {
  if (!window.Chart) return;
  const status = data.status || {};
  const statusColors = {PLANNED:'#9bb5ff',IN_PROGRESS:'#ec8b39',FINISHED:'#149b76',CANCELLED:'#9aa7ba',REOPENED:'#7b61d8'};
  financialDoughnut('operationStatusChart', status.labels, status.values, (status.keys || []).map(key => statusColors[key] || '#3867f4'), (status.keys || []).map(key => ({status:key})), false, true);
  const daily = data.daily || {};
  const dailyCanvas = document.getElementById('operationDailyChart');
  if (dailyCanvas) {
    dailyCanvas.dataset.financialChart = 'true';
    dailyCanvas.style.cursor = financialInteractionsEnabled() ? 'pointer' : 'default';
    new Chart(dailyCanvas, {type:'bar',data:{labels:daily.labels || [],datasets:[{label:'Trechos iniciados',data:daily.trips || [],backgroundColor:'#9bb5ff',borderRadius:6,yAxisID:'trips'},{label:'Km concluídos',data:daily.distance || [],type:'line',borderColor:'#149b76',backgroundColor:'rgba(20,155,118,.12)',fill:true,tension:.35,pointRadius:3,yAxisID:'distance'}]},options:{responsive:true,maintainAspectRatio:false,onClick:financialDrilldown((daily.dates || []).map(day => ({start:day,end:day}))),plugins:{legend:{position:'bottom',labels:{font:{family:'DM Sans'}}}},scales:{x:{grid:{display:false},ticks:{font:{family:'DM Sans'}}},trips:{beginAtZero:true,position:'left',grid:{color:financialChartGrid()},ticks:{precision:0,font:{family:'DM Sans'}}},distance:{beginAtZero:true,position:'right',grid:{drawOnChartArea:false},ticks:{font:{family:'DM Sans'},callback:value=>Number(value).toLocaleString('pt-BR')+' km'}}}}});
  }
  const trucks = data.trucks || {};
  financialBar('operationTruckChart', trucks.labels, trucks.distance, '#3867f4', (trucks.ids || []).map(id => ({truck:id})), false, (trucks.labels || []).length > 5);
  const drivers = data.drivers || {};
  financialBar('operationDriverChart', drivers.labels, drivers.distance, '#7b61d8', (drivers.ids || []).map(id => ({driver:id})), false, (drivers.labels || []).length > 5);
}

function fuelingManagementCharts(data) {
  if (!window.Chart) return;
  const monthly = data.monthly || {};
  const monthlyCanvas = document.getElementById('fuelMonthlyChart');
  if (monthlyCanvas) {
    monthlyCanvas.dataset.financialChart = 'true';
    monthlyCanvas.style.cursor = financialInteractionsEnabled() ? 'pointer' : 'default';
    new Chart(monthlyCanvas, {type:'bar',data:{labels:monthly.labels || [],datasets:[{label:'Gasto',data:monthly.amount || [],backgroundColor:'#ec8b39',borderRadius:6,yAxisID:'amount'},{label:'Litros',data:monthly.liters || [],type:'line',borderColor:'#3867f4',backgroundColor:'rgba(56,103,244,.1)',fill:true,tension:.35,pointRadius:3,yAxisID:'liters'}]},options:{responsive:true,maintainAspectRatio:false,onClick:financialDrilldown((monthly.starts || []).map((start,index) => ({start,end:(monthly.ends || [])[index]}))),plugins:{legend:{position:'bottom',labels:{font:{family:'DM Sans'}}},tooltip:{callbacks:{label:ctx=>ctx.dataset.label === 'Gasto' ? `Gasto: ${financialMoney(ctx.raw)}` : `Litros: ${Number(ctx.raw).toLocaleString('pt-BR')} L`}}},scales:{x:{grid:{display:false},ticks:{font:{family:'DM Sans'}}},amount:{beginAtZero:true,position:'left',grid:{color:financialChartGrid()},ticks:{font:{family:'DM Sans'},callback:financialMoney}},liters:{beginAtZero:true,position:'right',grid:{drawOnChartArea:false},ticks:{font:{family:'DM Sans'},callback:value=>Number(value).toLocaleString('pt-BR')+' L'}}}}});
  }
  const trucks = data.trucks || {};
  financialBar('fuelTruckChart', trucks.labels, trucks.amount, '#ec8b39', (trucks.ids || []).map(id => ({truck:id})), true, (trucks.labels || []).length > 5);
  const cities = data.cities || {};
  financialBar('fuelCityChart', cities.labels, cities.amount, '#7b61d8', (cities.cities || []).map(city => ({city})), true, (cities.labels || []).length > 5);
}

function maintenanceManagementCharts(data) {
  if (!window.Chart) return;
  const types = data.types || {};
  financialDoughnut('maintenanceTypeChart', types.labels, types.values, ['#df5b66','#ec8b39','#7b61d8','#3867f4','#149b76','#9aa7ba'], (types.keys || []).map(type => ({type})), true, true);
  const trucks = data.trucks || {};
  financialBar('maintenanceTruckChart', trucks.labels, trucks.values, '#df5b66', (trucks.ids || []).map(id => ({truck:id})), true, (trucks.labels || []).length > 5);
}

function cashflowCharts(data) {
  if (!window.Chart) return;
  const payable = '#df5b66';
  const receivable = '#149b76';
  const colors = (data.keys || []).map(key => key === 'RECEIVABLE' ? receivable : payable);
  financialDoughnut('cashCategoryChart', data.labels, data.values, colors, [], true, true);
}

initFinancialInteractionControls();
initAsyncFilters();
