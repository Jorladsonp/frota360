function initAppChrome() {
  if (document.documentElement.dataset.appChromeInitialized) return;
  document.documentElement.dataset.appChromeInitialized = 'true';
  const appShell = document.querySelector('.app-shell');
  const sidebar = document.getElementById('mainSidebar');
  const brandName = sidebar && sidebar.querySelector('.brand > span:not(.brand-mark)');
  if (brandName) brandName.classList.add('brand-name');
  const mobileToggle = document.querySelector('[data-sidebar-toggle]');
  if (mobileToggle && sidebar) mobileToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
  if (appShell && sidebar) {
    const collapse = document.createElement('button');
    collapse.type = 'button';
    collapse.className = 'btn sidebar-expand d-none d-lg-inline-flex';
    collapse.setAttribute('data-sidebar-collapse', '');
    collapse.setAttribute('aria-label', 'Abrir ou recolher menu');
    collapse.title = 'Abrir ou recolher menu';
    collapse.innerHTML = '<i class="bi bi-layout-sidebar-inset"></i>';
    const topbar = document.querySelector('.topbar');
    const context = document.querySelector('.topbar-context');
    if (topbar && context) topbar.insertBefore(collapse, context);
    let collapsed = false;
    try { collapsed = window.localStorage.getItem('frota360:sidebar') === 'collapsed'; } catch (error) { /* menu aberto por padrão */ }
    const setCollapsed = next => {
      appShell.classList.toggle('sidebar-collapsed', next);
      document.querySelectorAll('[data-sidebar-collapse]').forEach(button => {
        const icon = button.querySelector('i');
        if (icon && button.classList.contains('sidebar-collapse')) icon.className = next ? 'bi bi-chevron-right' : 'bi bi-chevron-left';
        button.setAttribute('aria-label', next ? 'Abrir menu' : 'Recolher menu');
        button.title = next ? 'Abrir menu' : 'Recolher menu';
      });
    };
    setCollapsed(collapsed);
    document.querySelectorAll('[data-sidebar-collapse]').forEach(button => button.addEventListener('click', () => {
      const next = !appShell.classList.contains('sidebar-collapsed');
      setCollapsed(next);
      try { window.localStorage.setItem('frota360:sidebar', next ? 'collapsed' : 'expanded'); } catch (error) { /* memória visual apenas */ }
    }));
  }
  const topbar = document.querySelector('.topbar');
  const userMenu = document.querySelector('.user-menu');
  if (topbar && userMenu && !document.querySelector('[data-theme-toggle]')) {
    const theme = document.createElement('button');
    theme.type = 'button';
    theme.className = 'theme-toggle';
    theme.setAttribute('data-theme-toggle', '');
    theme.innerHTML = '<i class="bi bi-moon-stars"></i><span data-theme-label>Modo escuro</span>';
    topbar.insertBefore(theme, userMenu);
    const applyTheme = dark => {
      document.documentElement.dataset.theme = dark ? 'dark' : 'light';
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
    window.location.assign(url.toString());
  };
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

initFinancialInteractionControls();
