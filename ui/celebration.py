"""One-shot local confetti; no external scripts or user text."""
import streamlit as st


def confetti():
    st.html('''<script>
    (() => {
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      document.getElementById('overlap-confetti')?.remove();
      const canvas = document.createElement('canvas');
      canvas.id = 'overlap-confetti';
      canvas.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:999999';
      canvas.setAttribute('aria-hidden', 'true');
      canvas.width = window.innerWidth; canvas.height = window.innerHeight;
      document.body.appendChild(canvas);
      const ctx = canvas.getContext('2d');
      const colors = ['#7047eb','#b59aff','#ffd166','#ef75b5','#68d7c2'];
      const pieces = Array.from({length:160}, () => ({
        x:Math.random()*canvas.width, y:-Math.random()*canvas.height,
        vx:(Math.random()-.5)*3, vy:2+Math.random()*4,
        angle:Math.random()*6.28, color:colors[Math.floor(Math.random()*colors.length)]
      }));
      const start = performance.now();
      let previous = start;
      function frame(now) {
        const dt = Math.min(3, (now-previous)/16.67); previous = now;
        ctx.clearRect(0,0,canvas.width,canvas.height);
        ctx.globalAlpha = Math.min(1, (4500-(now-start))/1000);
        for (const p of pieces) {
          p.x += p.vx*dt; p.y += p.vy*dt; p.angle += .06*dt;
          ctx.save(); ctx.translate(p.x,p.y); ctx.rotate(p.angle);
          ctx.fillStyle=p.color; ctx.fillRect(-4,-3,8,6); ctx.restore();
        }
        if (now-start < 4500) requestAnimationFrame(frame); else canvas.remove();
      }
      requestAnimationFrame(frame);
    })();
    </script>''', unsafe_allow_javascript=True)
