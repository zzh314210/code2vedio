// Official libraries, vendored with MIT licenses; JSON geometry in, paths out.
const rough = require('./vendor/handdrawn/rough.cjs');
const {getStroke} = require('./vendor/handdrawn/perfect-freehand.cjs');
const fs = require('fs');
const q = JSON.parse(fs.readFileSync(0, 'utf8'));
if (q.kind === 'ink') {
  const points = getStroke(q.points, {size:q.size, thinning:.5, smoothing:.5, streamline:.25, simulatePressure:q.simulatePressure, last:true});
  process.stdout.write(JSON.stringify({outline:points}));
} else {
  const g=rough.generator(); const p=q.points; const o=q.options; let shapes;
  switch(q.kind) {
    case 'rectangle': shapes=[g.rectangle(-q.width/2,-q.height/2,q.width,q.height,o)];break;
    case 'ellipse': shapes=[g.ellipse(0,0,q.width,q.height,o)];break;
    case 'polygon': shapes=[g.polygon(p,o)];break;
    case 'curve': shapes=[g.curve(p,o)];break;
    case 'line': shapes=[g.line(...p[0],...p[1],o)];break;
    case 'arrow': {
      const a=p[0],b=p[1],dx=b[0]-a[0],dy=b[1]-a[1],n=Math.hypot(dx,dy),s=Math.min(24,n*.2),ux=dx/n,uy=dy/n;
      shapes=[g.line(...a,...b,o),g.line(b[0]-s*ux+s*.5*uy,b[1]-s*uy-s*.5*ux,...b,o),g.line(b[0]-s*ux-s*.5*uy,b[1]-s*uy+s*.5*ux,...b,o)];break;
    }
    default: throw Error('Unsupported handdrawn primitive');
  }
  process.stdout.write(JSON.stringify({sets:shapes.flatMap(s=>s.sets)}));
}
