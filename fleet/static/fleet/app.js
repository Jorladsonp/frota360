document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('[data-sidebar-toggle]');
  const sidebar = document.getElementById('mainSidebar');
  if (toggle && sidebar) toggle.addEventListener('click', () => sidebar.classList.toggle('open'));
});

function fleetCharts(data, financed, paid, maintenance, breakdown = {}) {
  const chartFont = {family: 'DM Sans'};
  const revenueCanvas = document.getElementById('revenueChart');
  if (revenueCanvas && window.Chart) new Chart(revenueCanvas, {type:'line', data:{labels:data.labels,datasets:[{label:'Receita',data:data.revenue,borderColor:'#3867f4',backgroundColor:'rgba(56,103,244,.1)',fill:true,tension:.35,pointRadius:3},{label:'Custos',data:data.costs,borderColor:'#ec8b39',backgroundColor:'rgba(236,139,57,.04)',fill:true,tension:.35,pointRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:'#eef1f5'},ticks:{font:chartFont,callback:v=>'R$ '+Number(v).toLocaleString('pt-BR')}},x:{grid:{display:false},ticks:{font:chartFont}}}}});
  const fleetCanvas = document.getElementById('fleetChart');
  if (fleetCanvas && window.Chart) new Chart(fleetCanvas, {type:'doughnut',data:{labels:['Financiados','Quitados','Em manutenção'],datasets:[{data:[financed,paid,maintenance],backgroundColor:['#3867f4','#9bb5ff','#ec8b39'],borderWidth:0,hoverOffset:4}]},options:{cutout:'72%',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}});
  const makeBar = (id, labels, values, color, money = false) => {
    const canvas = document.getElementById(id);
    if (!canvas || !window.Chart) return;
    new Chart(canvas, {type:'bar', data:{labels:labels || [], datasets:[{data:values || [],backgroundColor:color,borderRadius:5,barThickness:18}]}, options:{responsive:true,maintainAspectRatio:false,indexAxis:(labels || []).length > 5 ? 'y' : 'x',plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx => (money ? 'R$ ' : '') + Number(ctx.raw).toLocaleString('pt-BR',{maximumFractionDigits:2})}}},scales:{x:{grid:{display:false},ticks:{font:chartFont}},y:{beginAtZero:true,grid:{color:'#eef1f5'},ticks:{font:chartFont,callback:v => money ? 'R$ '+Number(v).toLocaleString('pt-BR') : v}}}}});
  };
  makeBar('resultTruckChart', breakdown.truck_labels, breakdown.result_values, '#3867f4', true);
  makeBar('consumptionChart', breakdown.truck_labels, breakdown.km_l_values, '#149b76');
  makeBar('maintenanceChart', breakdown.truck_labels, breakdown.maintenance_values, '#df5b66', true);
  makeBar('productionChart', breakdown.contract_labels, breakdown.production_values, '#7b61d8', true);
  makeBar('remunerationChart', breakdown.driver_labels, breakdown.remuneration_values, '#ec8b39', true);
}

function costReportCharts(composition, trucks) {
  if (!window.Chart) return;
  const font = {family: 'DM Sans'};
  const compositionCanvas = document.getElementById('costCompositionChart');
  if (compositionCanvas) new Chart(compositionCanvas, {type:'bar', data:{labels:composition.labels,datasets:[{data:composition.values,backgroundColor:['#3867f4','#df5b66','#ec8b39','#7b61d8','#9bb5ff','#149b76'],borderRadius:6,barThickness:26}]}, options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>'R$ '+Number(ctx.raw).toLocaleString('pt-BR',{minimumFractionDigits:2})}}},scales:{y:{beginAtZero:true,grid:{color:'#eef1f5'},ticks:{font,callback:v=>'R$ '+Number(v).toLocaleString('pt-BR')}},x:{grid:{display:false},ticks:{font}}}}});
  const trucksCanvas = document.getElementById('truckCostChart');
  if (trucksCanvas) new Chart(trucksCanvas, {type:'bar', data:{labels:trucks.labels,datasets:[{data:trucks.values,backgroundColor:'#3867f4',borderRadius:6,barThickness:24}]}, options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>'R$ '+Number(ctx.raw).toLocaleString('pt-BR',{minimumFractionDigits:2})}}},scales:{y:{beginAtZero:true,grid:{color:'#eef1f5'},ticks:{font,callback:v=>'R$ '+Number(v).toLocaleString('pt-BR')}},x:{grid:{display:false},ticks:{font}}}}});
}

function resultReportCharts(comparison, monthly) {
  if (!window.Chart) return;
  const font = {family: 'DM Sans'};
  const money = value => 'R$ '+Number(value).toLocaleString('pt-BR',{minimumFractionDigits:2});
  const comparisonCanvas = document.getElementById('resultComparisonChart');
  if (comparisonCanvas) new Chart(comparisonCanvas, {type:'bar', data:{labels:comparison.labels,datasets:[{label:'Receita',data:comparison.revenue,backgroundColor:'#3867f4',borderRadius:5},{label:'Custos',data:comparison.cost,backgroundColor:'#ec8b39',borderRadius:5},{label:'Resultado',data:comparison.result,backgroundColor:'#149b76',borderRadius:5}]}, options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font}},tooltip:{callbacks:{label:ctx=>ctx.dataset.label+': '+money(ctx.raw)}}},scales:{y:{beginAtZero:true,grid:{color:'#eef1f5'},ticks:{font,callback:v=>'R$ '+Number(v).toLocaleString('pt-BR')}},x:{grid:{display:false},ticks:{font}}}}});
  const monthlyCanvas = document.getElementById('monthlyResultChart');
  if (monthlyCanvas) new Chart(monthlyCanvas, {type:'line', data:{labels:monthly.labels,datasets:[{label:'Receita',data:monthly.revenue,borderColor:'#3867f4',backgroundColor:'rgba(56,103,244,.09)',fill:true,tension:.35,pointRadius:3},{label:'Custos',data:monthly.costs,borderColor:'#ec8b39',backgroundColor:'rgba(236,139,57,.05)',fill:true,tension:.35,pointRadius:3},{label:'Resultado',data:monthly.result,borderColor:'#149b76',backgroundColor:'transparent',tension:.35,pointRadius:3}]}, options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font}},tooltip:{callbacks:{label:ctx=>ctx.dataset.label+': '+money(ctx.raw)}}},scales:{y:{grid:{color:'#eef1f5'},ticks:{font,callback:v=>'R$ '+Number(v).toLocaleString('pt-BR')}},x:{grid:{display:false},ticks:{font}}}}});
}
