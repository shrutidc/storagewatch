import { useEffect, useRef } from 'react'

// Drifting points joined by lines when they come near each other — a quiet
// nod to disks and the links between them, behind the sign-in card.
//
// Drawn on a canvas rather than as DOM nodes: a hundred animated elements
// would each need layout and paint every frame, where a canvas is one.
function LoginParticles() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    // Someone who has asked for less motion gets a still background.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const ctx = canvas.getContext('2d')

    // Canvas takes colours as strings, not CSS variables, so the tokens are
    // read once and again whenever the theme attribute changes.
    let dot = '#7c8cf8'
    let line = '124,140,248'
    const readColours = () => {
      const css = getComputedStyle(document.documentElement)
      dot = css.getPropertyValue('--circuit-pulse').trim() || dot
      line = css.getPropertyValue('--circuit-line-rgb').trim() || line
    }
    readColours()
    const themeWatcher = new MutationObserver(readColours)
    themeWatcher.observe(document.documentElement, {
      attributes: true, attributeFilter: ['data-theme'],
    })

    let width = 0
    let height = 0
    let points = []
    let frame

    // Enough to feel alive, few enough that the O(n²) neighbour check below
    // stays cheap; scaled to the window so a large display isn't sparse.
    const countFor = (w, h) => Math.min(90, Math.round((w * h) / 18000))

    const resize = () => {
      // Backing store in device pixels, drawing coordinates in CSS pixels, so
      // the lines aren't soft on a Retina screen.
      const ratio = window.devicePixelRatio || 1
      width = canvas.clientWidth
      height = canvas.clientHeight
      canvas.width = width * ratio
      canvas.height = height * ratio
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0)

      points = Array.from({ length: countFor(width, height) }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        r: Math.random() * 1.8 + 0.9,
      }))
    }

    const LINK_DISTANCE = 130

    const draw = () => {
      ctx.clearRect(0, 0, width, height)

      for (const p of points) {
        p.x += p.vx
        p.y += p.vy
        // Wrap rather than bounce: bouncing collects points along the edges.
        if (p.x < -10) p.x = width + 10
        if (p.x > width + 10) p.x = -10
        if (p.y < -10) p.y = height + 10
        if (p.y > height + 10) p.y = -10
      }

      for (let i = 0; i < points.length; i++) {
        for (let j = i + 1; j < points.length; j++) {
          const dx = points[i].x - points[j].x
          const dy = points[i].y - points[j].y
          const dist = Math.hypot(dx, dy)
          if (dist > LINK_DISTANCE) continue
          // Fades out as they separate, so links appear and dissolve rather
          // than blinking on and off at the threshold.
          ctx.strokeStyle = `rgba(${line},${(1 - dist / LINK_DISTANCE) * 0.42})`
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(points[i].x, points[i].y)
          ctx.lineTo(points[j].x, points[j].y)
          ctx.stroke()
        }
      }

      ctx.fillStyle = dot
      for (const p of points) {
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fill()
      }

      frame = requestAnimationFrame(draw)
    }

    resize()
    draw()
    window.addEventListener('resize', resize)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', resize)
      themeWatcher.disconnect()
    }
  }, [])

  return <canvas ref={canvasRef} className="login-particles" aria-hidden="true" />
}

export default LoginParticles
