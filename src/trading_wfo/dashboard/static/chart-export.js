function downloadDataUrl(dataUrl,filename){const link=document.createElement('a');link.href=dataUrl;link.download=filename;document.body.append(link);link.click();link.remove()}
function canvasFilename(canvas){return `${canvas.id||'chart'}.png`}
function saveCanvas(canvas){downloadDataUrl(canvas.toDataURL('image/png'),canvasFilename(canvas))}
async function saveTradeChart(){const plot=document.querySelector('#trade-plot');if(!plot||!plot.data?.length)return;const url=await Plotly.toImage(plot,{format:'png',width:1600,height:Math.max(700,plot.clientHeight*2),scale:1});downloadDataUrl(url,`trade-${state.selectedTradeData?.position_id??'chart'}.png`)}
function loadExportImage(url){return new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=reject;image.src=url})}
async function saveAllCharts(){
  const assets=[...document.querySelectorAll('canvas')].map(canvas=>({name:canvas.id||'Chart',image:canvas,width:canvas.width,height:canvas.height}));
  const plot=document.querySelector('#trade-plot');
  if(plot?.data?.length){const url=await Plotly.toImage(plot,{format:'png',width:1600,height:Math.max(700,plot.clientHeight*2),scale:1});const image=await loadExportImage(url);assets.push({name:'Trade chart',image,width:image.naturalWidth,height:image.naturalHeight})}
  if(!assets.length)return;
  const width=Math.max(...assets.map(asset=>asset.width),900),gap=48,labelHeight=38;
  const height=assets.reduce((total,asset)=>total+asset.height+labelHeight+gap,24);
  const output=document.createElement('canvas');output.width=width;output.height=height;
  const context=output.getContext('2d');context.fillStyle=themeColor('--chart-bg');context.fillRect(0,0,width,height);context.fillStyle=themeColor('--chart-text');context.font='600 24px system-ui';
  let y=24;for(const asset of assets){context.fillText(asset.name,20,y+25);y+=labelHeight;context.drawImage(asset.image,0,y,asset.width,asset.height);y+=asset.height+gap}
  downloadDataUrl(output.toDataURL('image/png'),'trading-wfo-all-charts.png');
}
function installChartExportButtons(){document.querySelectorAll('.panel').forEach(panel=>{const canvas=panel.querySelector('canvas'),heading=panel.querySelector('.panel-heading');if(!canvas||!heading||heading.querySelector('.save-canvas-chart'))return;const button=el('button','Save PNG','control-button save-canvas-chart');button.type='button';button.addEventListener('click',()=>saveCanvas(canvas));heading.append(button)});document.querySelector('#save-all-charts')?.addEventListener('click',saveAllCharts);document.querySelector('#save-trade-chart')?.addEventListener('click',saveTradeChart)}
installChartExportButtons();
