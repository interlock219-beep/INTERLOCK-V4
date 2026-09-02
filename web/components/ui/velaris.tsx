"use client"

import { cn } from "@/lib/utils"
import { useEffect, useRef, useState } from "react"

interface VelarisProps {
  className?: string
}

const VERTEX_SHADER_SOURCE = `
precision highp float;
attribute vec3 a_position;
uniform float u_spin;
uniform float u_tiltSin;
uniform float u_tiltCos;
uniform float u_focal;
uniform float u_scale;
uniform float u_pointSize;
uniform bool u_points;
varying float v_depth;
void main() {
  float x = a_position.x;
  float y = a_position.y;
  float z = a_position.z;
  float c = cos(u_spin);
  float s = sin(u_spin);
  float rx = x * c - z * s;
  float rz = x * s + z * c;
  float ry = y * u_tiltCos - rz * u_tiltSin;
  float rz2 = y * u_tiltSin + rz * u_tiltCos;
  float persp = u_focal / (u_focal + rz2);
  v_depth = persp;
  if (u_points) {
    gl_PointSize = u_pointSize * persp;
  }
  gl_Position = vec4(rx * persp * u_scale, ry * persp * u_scale, clamp((rz2 + u_focal) / (u_focal * 2.0), 0.0, 1.0), 1.0);
}
`

const FRAGMENT_SHADER_SOURCE = `
precision mediump float;
uniform vec3 u_color;
uniform float u_alpha;
uniform float u_time;
uniform bool u_points;
varying float v_depth;
void main() {
  float breath = 0.92 + 0.08 * sin(u_time * 0.6);
  if (u_points) {
    float d = length(gl_PointCoord - 0.5);
    float a = 1.0 - smoothstep(0.45, 0.5, d);
    gl_FragColor = vec4(u_color, u_alpha * a * v_depth * breath);
  } else {
    float fade = smoothstep(4.0, 0.0, -v_depth * 3.0 + 3.0);
    gl_FragColor = vec4(u_color, u_alpha * fade * breath);
  }
}
`

interface VelarisHandles {
  gl: WebGL2RenderingContext
  canvas: HTMLCanvasElement
  program: WebGLProgram
  positionLoc: GLint
  timeLoc: WebGLUniformLocation
  spinLoc: WebGLUniformLocation
  tiltSinLoc: WebGLUniformLocation
  tiltCosLoc: WebGLUniformLocation
  focalLoc: WebGLUniformLocation
  scaleLoc: WebGLUniformLocation
  pointSizeLoc: WebGLUniformLocation
  pointsLoc: WebGLUniformLocation
  colorLoc: WebGLUniformLocation
  alphaLoc: WebGLUniformLocation
  edgeVao: WebGLVertexArrayObject
  nodeVao: WebGLVertexArrayObject
  edgeCount: number
  nodeCount: number
}

function createShader(
  gl: WebGL2RenderingContext,
  source: string,
  type: number,
): WebGLShader | null {
  const shader = gl.createShader(type)
  if (!shader) return null
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader)
    return null
  }
  return shader
}

interface Lattice {
  nodePositions: Float32Array
  edgeVertices: Float32Array
  nodeCount: number
  edgeCount: number
}

function buildLattice(): Lattice {
  const segments = 14
  const rings = 8
  const radius = 2.7
  const height = 3.6
  const depth = 0.6

  const nodePositions: number[] = []
  const nodeIndex = (r: number, s: number) => r * segments + s

  for (let r = 0; r < rings; r++) {
    for (let s = 0; s < segments; s++) {
      const angle = (s / segments) * Math.PI * 2
      const y = (r / (rings - 1) - 0.5) * height
      nodePositions.push(
        Math.cos(angle) * radius,
        y,
        Math.sin(angle) * radius - depth,
      )
    }
  }

  const edgeVertices: number[] = []
  const pushEdge = (i: number, j: number) => {
    edgeVertices.push(
      nodePositions[i * 3],
      nodePositions[i * 3 + 1],
      nodePositions[i * 3 + 2],
      nodePositions[j * 3],
      nodePositions[j * 3 + 1],
      nodePositions[j * 3 + 2],
    )
  }
  for (let r = 0; r < rings; r++) {
    for (let s = 0; s < segments; s++) {
      const a = nodeIndex(r, s)
      pushEdge(a, nodeIndex(r, (s + 1) % segments))
      if (r + 1 < rings) pushEdge(a, nodeIndex(r + 1, s))
    }
  }

  return {
    nodePositions: new Float32Array(nodePositions),
    edgeVertices: new Float32Array(edgeVertices),
    nodeCount: nodePositions.length / 3,
    edgeCount: edgeVertices.length / 3,
  }
}

export function Velaris({ className }: VelarisProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const handlesRef = useRef<VelarisHandles | null>(null)
  const rafRef = useRef<number>(0)
  const observerRef = useRef<ResizeObserver | null>(null)
  const reducedRef = useRef(false)
  const [mounted, setMounted] = useState(false)

  useEffect(() => setMounted(true), [])

  useEffect(() => {
    if (!mounted || !containerRef.current) return

    const container = containerRef.current
    reducedRef.current = window
      .matchMedia("(prefers-reduced-motion: reduce)")
      .matches

    const canvas = document.createElement("canvas")
    canvas.style.display = "block"
    canvas.style.width = "100%"
    canvas.style.height = "100%"

    const gl = canvas.getContext("webgl2", {
      alpha: true,
      depth: true,
      antialias: true,
      preserveDrawingBuffer: false,
    })

    // WebGL unavailable — leave the container's CSS background visible.
    if (!gl) return

    const vs = createShader(gl, VERTEX_SHADER_SOURCE, gl.VERTEX_SHADER)
    const fs = createShader(gl, FRAGMENT_SHADER_SOURCE, gl.FRAGMENT_SHADER)
    if (!vs || !fs) {
      gl.deleteShader(vs)
      gl.deleteShader(fs)
      return
    }

    const program = gl.createProgram()
    if (!program) {
      gl.deleteShader(vs)
      gl.deleteShader(fs)
      return
    }
    gl.attachShader(program, vs)
    gl.attachShader(program, fs)
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      gl.deleteProgram(program)
      gl.deleteShader(vs)
      gl.deleteShader(fs)
      return
    }
    gl.deleteShader(vs)
    gl.deleteShader(fs)

    const uniform = (name: string) => gl.getUniformLocation(program, name)!
    const { nodePositions, edgeVertices, nodeCount, edgeCount } = buildLattice()

    const positionLoc = gl.getAttribLocation(program, "a_position")
    const handles: VelarisHandles = {
      gl,
      canvas,
      program,
      positionLoc,
      timeLoc: uniform("u_time"),
      spinLoc: uniform("u_spin"),
      tiltSinLoc: uniform("u_tiltSin"),
      tiltCosLoc: uniform("u_tiltCos"),
      focalLoc: uniform("u_focal"),
      scaleLoc: uniform("u_scale"),
      pointSizeLoc: uniform("u_pointSize"),
      pointsLoc: uniform("u_points"),
      colorLoc: uniform("u_color"),
      alphaLoc: uniform("u_alpha"),
      edgeVao: gl.createVertexArray()!,
      nodeVao: gl.createVertexArray()!,
      edgeCount,
      nodeCount,
    }
    handlesRef.current = handles

    const bindVao = (vao: WebGLVertexArrayObject, data: Float32Array) => {
      gl.bindVertexArray(vao)
      const buf = gl.createBuffer()
      gl.bindBuffer(gl.ARRAY_BUFFER, buf)
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW)
      gl.enableVertexAttribArray(positionLoc)
      gl.vertexAttribPointer(positionLoc, 3, gl.FLOAT, false, 0, 0)
    }
    bindVao(handles.edgeVao, edgeVertices)
    bindVao(handles.nodeVao, nodePositions)

    gl.useProgram(program)
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
    gl.enable(gl.DEPTH_TEST)
    gl.depthFunc(gl.LEQUAL)
    gl.clearColor(0.02, 0.025, 0.03, 1)
    gl.viewport(0, 0, canvas.width, canvas.height)

    container.appendChild(canvas)

    let disposed = false
    const tickInterval = 1000 / 30
    let last = 0

    const resize = () => {
      const rect = container.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const w = Math.max(1, Math.round(rect.width * dpr))
      const h = Math.max(1, Math.round(rect.height * dpr))
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w
        canvas.height = h
      }
      gl.viewport(0, 0, canvas.width, canvas.height)
    }

    observerRef.current = new ResizeObserver(() => resize())
    observerRef.current.observe(container)
    window.addEventListener("resize", resize)
    resize()

    const tick = (now: number) => {
      if (disposed) return
      if (now - last < tickInterval && document.visibilityState === "visible") {
        rafRef.current = requestAnimationFrame(tick)
        return
      }
      last = now

      const reduced = reducedRef.current
      const t = now * 0.001

      gl.useProgram(handles.program)
      gl.uniform1f(handles.timeLoc, t)
      gl.uniform1f(handles.spinLoc, t * (reduced ? 0.03 : 0.08))
      gl.uniform1f(handles.tiltSinLoc, reduced ? 0 : Math.sin(t * 0.12) * 0.08)
      gl.uniform1f(
        handles.tiltCosLoc,
        reduced ? 1 : Math.cos(t * 0.12) * 0.08 + 0.996,
      )
      gl.uniform1f(handles.focalLoc, 6)
      gl.uniform1f(handles.scaleLoc, 0.42)
      gl.uniform1f(handles.pointSizeLoc, reduced ? 0 : 56)

      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT)

      if (document.visibilityState === "hidden") {
        rafRef.current = requestAnimationFrame(tick)
        return
      }

      const edgeColor = reduced ? [0.13, 0.55, 0.48] : [0.16, 0.7, 0.58]
      const nodeColor = [0.16, 0.7, 0.58]

      gl.uniform1i(handles.pointsLoc, 0)
      gl.uniform3fv(handles.colorLoc, edgeColor)
      gl.uniform1f(handles.alphaLoc, reduced ? 0.12 : 0.22)
      gl.bindVertexArray(handles.edgeVao)
      gl.drawArrays(gl.LINES, 0, handles.edgeCount)

      gl.uniform1i(handles.pointsLoc, 1)
      gl.uniform3fv(handles.colorLoc, nodeColor)
      gl.uniform1f(handles.alphaLoc, reduced ? 0.4 : 0.7)
      gl.bindVertexArray(handles.nodeVao)
      gl.drawArrays(gl.POINTS, 0, handles.nodeCount)

      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)

    return () => {
      disposed = true
      cancelAnimationFrame(rafRef.current)
      observerRef.current?.disconnect()
      window.removeEventListener("resize", resize)
      gl.deleteVertexArray(handles.edgeVao)
      gl.deleteVertexArray(handles.nodeVao)
      gl.deleteProgram(handles.program)
      handlesRef.current = null
      canvas.remove()
    }
  }, [mounted])

  return (
    <div
      ref={containerRef}
      className={cn(
        "absolute inset-0 overflow-hidden pointer-events-none",
        "bg-[radial-gradient(ellipse_at_center,rgba(16,185,129,0.06),transparent_55%)]",
        className,
      )}
      aria-hidden="true"
    />
  )
}
