/**
 * Canvas Engine - TypeScript port (permissive types)
 * Kept lightweight: most Konva objects typed as `any` to allow incremental migration.
 */

import Konva from 'konva'
import { rootCertificates } from 'tls';

export class CanvasEngine {
  stage: Konva.Stage;
  imageLayer: Konva.Layer;
  cropLayer: Konva.Layer;
  transformer: Konva.Transformer;
  transformerAdded: boolean;
  activeTool: string | null;
  currentImage: Konva.Image | null;
  originalDimensions: { width: number; height: number };
  displayScale: number;
  imageScale: number;
  combinedScale: number;
  minZoomScale: number;
  listeners: Map<string, Array<(...args: unknown[]) => void>>;
  isPanning: boolean;
  lastPosX: number;
  lastPosY: number;
  private _transformReady: boolean;

  constructor(canvasElement: HTMLCanvasElement, options: Record<string, unknown> = {}) {
    const wrapper = canvasElement.parentElement
    if (!wrapper) throw new Error('Canvas element must be attached to a parent element')

    this.stage = new Konva.Stage({
      container: wrapper as HTMLDivElement,
      width: (canvasElement as HTMLCanvasElement).width || 800,
      height: (canvasElement as HTMLCanvasElement).height || 600
    })

    canvasElement.style.display = 'none'

    this.imageLayer = new Konva.Layer()
    this.cropLayer = new Konva.Layer()

    this.stage.add(this.imageLayer)
    this.stage.add(this.cropLayer)

    this.transformer = new Konva.Transformer({
      borderStroke: '#3b82f6',
      borderStrokeWidth: 1,
      anchorFill: '#3b82f6',
      anchorStroke: '#fff',
      anchorStrokeWidth: 1,
      anchorSize: 8,
      anchorCornerRadius: 4,
      borderDash: [5, 5],
      keepRatio: false,
      enabledAnchors: [
        'top-left',
        'top-center',
        'top-right',
        'middle-right',
        'middle-left',
        'bottom-left',
        'bottom-center',
        'bottom-right'
      ],
      rotateEnabled: true,
      flipEnabled: false
    })

    this.transformerAdded = false

    this.activeTool = null
    this.currentImage = null
    this.originalDimensions = { width: 0, height: 0 }
    this.displayScale = 1
    this.imageScale = 1
    this.combinedScale = 1
    this.minZoomScale = 1
    this.listeners = new Map()
    this.isPanning = false
    this.lastPosX = 0
    this.lastPosY = 0
    this._transformReady = false

    this._setupEvents()
    this._setupZoomPan()
  }

  async loadImage(url: string, originalWidth: number | null = null) {
    return new Promise<void>((resolve, reject) => {
      const imageObj = new Image()
      imageObj.crossOrigin = 'anonymous'

      imageObj.onload = async () => {
        // Reset transform ready state for new image
        this._transformReady = false;
        
        // Yield one animation frame so the browser can paint any pending
        // UI changes (spinner / placeholder) before running expensive
        // synchronous Konva operations below.
        await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
        this.imageLayer.destroyChildren()

        const crops = this.cropLayer.find?.('.cropBox') ?? []
        crops.forEach((crop: Konva.Node) => crop.destroy())

        this.transformer.nodes([])

        if (originalWidth) {
          this.originalDimensions = {
            width: originalWidth,
            height: imageObj.height * (originalWidth / imageObj.width)
          }
        } else {
          this.originalDimensions = { width: imageObj.width, height: imageObj.height }
        }

        const imageScale = originalWidth ? imageObj.width / originalWidth : 1

        const container = this.stage.container()
        const containerWidth = container.clientWidth - 40
        const containerHeight = container.clientHeight - 40

        const scaleX = containerWidth / imageObj.width
        const scaleY = containerHeight / imageObj.height
        const displayScale = Math.min(scaleX, scaleY, 1)
        this.displayScale = displayScale
        this.imageScale = imageScale
        this.combinedScale = imageScale * displayScale
        this.minZoomScale = 1

        const canvasWidth = imageObj.width * displayScale
        const canvasHeight = imageObj.height * displayScale

        this.stage.width(canvasWidth)
        this.stage.height(canvasHeight)

        this.currentImage = new Konva.Image({
          image: imageObj,
          x: 0,
          y: 0,
          width: imageObj.width,
          height: imageObj.height,
          scaleX: displayScale,
          scaleY: displayScale,
          draggable: false,
          listening: false,
          offsetX: 0,
          offsetY: 0,
          rotation: 0
        })

        // Ensure the image node is centered in the stage and has proper
        // offset values so bbox coordinate mapping is consistent for both
        // rotated and unrotated images. This mirrors the attributes set
        // by applyRotation for non-zero rotations.
        try {
          const centerX = (imageObj.width * displayScale) / 2
          const centerY = (imageObj.height * displayScale) / 2
          this.currentImage.offsetX(imageObj.width / 2)
          this.currentImage.offsetY(imageObj.height / 2)
          this.currentImage.x(centerX)
          this.currentImage.y(centerY)
        } catch (e) {
          // ignore if Konva methods unavailable
        }

        // Ensure filters/defaults are neutral for each newly loaded image
        try {
          this.currentImage.filters([])
        } catch (err) {
          // Some Konva versions might not expose filters() until cached
        }
        // Ensure brightness/contrast attributes are neutral
        try {
          if (typeof (this.currentImage as any).brightness === 'function') (this.currentImage as any).brightness(0)
          if (typeof (this.currentImage as any).contrast === 'function') (this.currentImage as any).contrast(0)
        } catch (err) {
          // ignore
        }

        this.imageLayer.add(this.currentImage)
        this.imageLayer.batchDraw()

        // Cache the image once so Konva filters can operate without
        // re-caching on every small adjustment (which is expensive).
        // Defer caching to idle time so the initial paint isn't blocked.
        try {
          const scheduleIdle = (fn: () => void) => {
            if (typeof (window as any).requestIdleCallback === 'function') {
              (window as any).requestIdleCallback(() => fn(), { timeout: 500 })
            } else {
              // Fallback: small timeout to yield to browser paint
              setTimeout(fn, 50)
            }
          }
          scheduleIdle(() => {
            try { this.currentImage?.cache() } catch (err) { console.warn('Image caching failed:', err) }
          })
        } catch (err) {
          // Fail silently if scheduling is unavailable
        }

        // Debug: log current filters/values to help diagnose bright image issues
        try {
          // setTimeout to let any async setAttrs settle
          setTimeout(() => {
            console.log('CanvasEngine: loaded image filters', this.getFilters())
          }, 20)
        } catch (err) {
          // ignore
        }

        this.resetZoom()

        this._emit('imageLoaded', { width: canvasWidth, height: canvasHeight })
        
        // Set state to true BEFORE emitting event
        // This ensures late subscribers can query the state
        setTimeout(() => {
          const ready = this.isTransformReady();
          if (ready) {
            this._transformReady = true;
            this._emit('transformReady', { width: canvasWidth, height: canvasHeight })
          }
        }, 0)
        
        resolve()
      }

      imageObj.onerror = () => {
        reject(new Error('Failed to load image'))
      }

      imageObj.src = url
    })
  }

  activateTool(toolName: string) {
    this.deactivateTool()

    switch (toolName) {
      case 'crop':
        this._activateCropTool()
        break
      case 'select':
        break
      default:
        console.warn(`Unknown tool: ${toolName}`)
    }

    this.activeTool = toolName
    this._emit('toolActivated', { tool: toolName })
  }

  deactivateTool() {
    this.activeTool = null
  }

  addCropBox(options: any = {}) {
    const defaultOptions = { x: 50, y: 50, width: 300, height: 400, autoSelect: true }
    const finalOptions = { ...defaultOptions, ...options }
    const autoSelect = finalOptions.autoSelect
    delete finalOptions.autoSelect

    // Ensure only one crop box exists: remove any existing ones
    try {
      const existing = this.cropLayer.find('.cropBox') || [];
      existing.forEach((n: Konva.Node) => n.destroy());
      // Clear transformer selection
      this.transformer.nodes([]);
    } catch (e) {}

    const rect = new Konva.Rect({
      x: finalOptions.x,
      y: finalOptions.y,
      width: finalOptions.width,
      height: finalOptions.height,
      fill: 'rgba(59, 130, 246, 0.15)',
      stroke: '#3b82f6',
      strokeWidth: 2,
      strokeScaleEnabled: false,
      dash: [4, 4],
      draggable: true,
      name: 'cropBox'
    })

    rect.on('click tap', () => {
      this.transformer.nodes([rect])
      this.transformer.forceUpdate()
      this.cropLayer.batchDraw()
    })

    rect.on('dragend transformend', () => {
      this._emit('modified', { source: 'user' })
    })

    this.cropLayer.add(rect)

    if (!this.transformerAdded) {
      this.cropLayer.add(this.transformer)
      this.transformerAdded = true
      this.cropLayer.batchDraw()
    }

    if (autoSelect) {
      this.transformer.nodes([rect])
      this.transformer.forceUpdate()
    }

    this.cropLayer.batchDraw()

    this._emit('objectAdded', { type: 'cropBox' })
    return rect
  }
  getCropBoxesForOriginal() {
    const boxesInfo = this.getCropBoxesInfoForOriginal();
    //Rounding the bbox values
    if (!boxesInfo || boxesInfo.length === 0) return [];
    const info = boxesInfo[0];
    return [{
      x: Math.round(info.bbox.x),
      y: Math.round(info.bbox.y),
      w: Math.round(info.bbox.w),
      h: Math.round(info.bbox.h)
    }];
  }
  getCropBoxesInfoForOriginal() {
    const imgNode = this.currentImage
    if (!imgNode) return null
    
    // CRITICAL: Check transform readiness FIRST
    // Return null (not []) to signal "engine not ready" vs "user has zero crops"
    try {
      if (typeof (this as any).isTransformReady === 'function') {
        if (!(this as any).isTransformReady()) {
          console.debug('getCropBoxesInfoForOriginal: transform not ready, returning null')
          return null
        }
      } else {
        // Fallback check
        const el = this._getImageElement()
        if (!el || el.width === 0) {
          console.debug('getCropBoxesInfoForOriginal: image element not ready, returning null')
          return null
        }
      }
    } catch (e) {
      console.debug('getCropBoxesInfoForOriginal: readiness check failed, returning null')
      return null
    }
    
    // Transform is ready. Now check actual crop boxes.
    const crops = this.cropLayer.find('.cropBox')
    // Empty array is a valid state: user intentionally has no crops
    if (crops.length === 0) {
      console.debug('getCropBoxesInfoForOriginal: transform ready, but no crop boxes exist (valid state)')
      return []
    }

    const combinedScale = this.combinedScale || this.displayScale * this.imageScale
    const displayScale = this.displayScale || 1

    const rad = (imgNode.rotation() * Math.PI) / 180
    const rotatedW_UI = (Math.abs(imgNode.width() * Math.cos(rad)) + Math.abs(imgNode.height() * Math.sin(rad))) * displayScale
    const rotatedH_UI = (Math.abs(imgNode.width() * Math.sin(rad)) + Math.abs(imgNode.height() * Math.cos(rad))) * displayScale

    const topLeftX = imgNode.x() - rotatedW_UI / 2
    const topLeftY = imgNode.y() - rotatedH_UI / 2

    const cropData = crops.map((rect: any) => {
      const localTL = rect.position()

      const x_display = localTL.x
      const y_display = localTL.y

      // Preserve width/height calculation from original implementation
      const w_display = rect.width() * rect.scaleX()
      const h_display = rect.height() * rect.scaleY()

      const x = x_display / combinedScale
      const y = y_display / combinedScale
      const w = w_display / combinedScale
      const h = h_display / combinedScale

      const bbox = { x: x, y: y, w: w, h: h }

      return {
        bbox: bbox,
        offsetX: -topLeftX / combinedScale,
        offsetY: -topLeftY / combinedScale,
      }
    })
    try { console.groupEnd() } catch (e) {}
    return cropData;
  }

  isTransformReady(): boolean {
    // Return stored state (persistent lifecycle state, not transient event)
    // Validation logic below acts as safety check but state is authoritative
    if (this._transformReady) return true;
    
    // Fallback validation for edge cases where state wasn't set yet
    try {
      if (!this.currentImage) return false
      const imgEl = this._getImageElement()
      if (!imgEl || !imgEl.width) return false
      const w = typeof (this.currentImage as any).width === 'function' ? (this.currentImage as any).width() : (this.currentImage as any).width
      const h = typeof (this.currentImage as any).height === 'function' ? (this.currentImage as any).height() : (this.currentImage as any).height
      // Offsets may legitimately be zero for unrotated images; only require
      // that the image element and dimensions are present to consider the
      // transform ready.
      return !!imgEl && !!w && !!h
    } catch (e) {
      return false
    }
  }

  loadCropBoxes(boxes: Array<any>) {
    // Only load the first box to enforce single-crop behavior
    const toLoad = (boxes && boxes.length > 0) ? [boxes[0]] : [];
    toLoad.forEach(box => {
      const scale = this.combinedScale || this.displayScale || 1

      console.group('📦 Loading Bbox')
      console.log('Original bbox (metadata):', box)

      const scaledBox = { x: box.x * scale, y: box.y * scale, width: box.w * scale, height: box.h * scale, autoSelect: false }
      console.log('Scaled bbox (applied to UI):', scaledBox, 'scale:', scale)

      console.groupEnd()

      // addCropBox will remove any existing boxes before adding
      this.addCropBox(scaledBox)
    })
    // Ensure the cropLayer is rendered synchronously so callers that
    // immediately query crop boxes (e.g. export readiness checks)
    // will observe the new nodes. Batch-draw may be deferred, so
    // force a draw and emit a modified event for listeners.
    try {
      this.cropLayer.draw()
    } catch (e) {
      // ignore draw errors
    }
    // This call originates from programmatic loading of saved bbox metadata.
    // Consumers can inspect `data.source` to distinguish user edits from
    // non-user-edit lifecycle operations.
    this._emit('modified', { source: 'programmatic' })
  }

  zoomIn() {
    const oldScale = this.stage.scaleX()
    const newScale = Math.min(oldScale * 1.1, 5)
    const center = { x: this.stage.width() / 2, y: this.stage.height() / 2 }
    this._zoomToPoint(center, newScale)
    this._emit('zoomChanged', { zoom: newScale })
  }

  zoomOut() {
    const oldScale = this.stage.scaleX()
    const newScale = Math.max(oldScale * 0.9, this.minZoomScale)
    const center = { x: this.stage.width() / 2, y: this.stage.height() / 2 }
    this._zoomToPoint(center, newScale)
    this._emit('zoomChanged', { zoom: newScale })
  }

  resetZoom() {
    this.stage.scale({ x: 1, y: 1 })
    this.centerView()
    this._emit('zoomChanged', { zoom: 1 })
  }

  centerView() {
    if (!this.currentImage) return

    const stageWidth = this.stage.width()
    const stageHeight = this.stage.height()
    const scale = this.stage.scaleX()

    const imageWidth = this.currentImage.width() * this.currentImage.scaleX() * scale
    const imageHeight = this.currentImage.height() * this.currentImage.scaleY() * scale

    const x = (stageWidth - imageWidth) / 2
    const y = (stageHeight - imageHeight) / 2

    this.stage.position({ x: imageWidth > stageWidth ? 0 : Math.max(0, x), y: imageHeight > stageHeight ? 0 : Math.max(0, y) })
    this.stage.batchDraw()
  }

  fitToCanvas() {
    this.resetZoom()
  }

  resetView() {
    this.resetZoom()
  }

  getZoom() {
    return this.stage.scaleX()
  }

  deleteSelected() {
    const selected = this.transformer.nodes()
    if (selected.length > 0) {
      selected.forEach((node: Konva.Node) => node.destroy())
      this.transformer.nodes([])
      this.cropLayer.batchDraw()
      this._emit('objectDeleted', { source: 'user' })
    }
  }

  clear() {
    const crops = this.cropLayer.find('.cropBox')
    crops.forEach((crop: Konva.Node) => crop.destroy())
    this.transformer.nodes([])
    this.cropLayer.batchDraw()
    this._emit('cleared', { source: 'programmatic' })
  }

  getScaleFactor() {
    if (!this.currentImage) return 1
    return this.originalDimensions.width / this.stage.width()
  }

  toDataURL(options: { format?: string; quality?: number } = {}) {
    const { format = 'png', quality = 1 } = options

    const currentScale = this.stage.scaleX()
    const currentPos = this.stage.position()

    this.stage.scale({ x: 1, y: 1 })
    this.stage.position({ x: 0, y: 0 })

    const dataUrl = this.imageLayer.toDataURL({ pixelRatio: 1, mimeType: `image/${format}`, quality })

    this.stage.scale({ x: currentScale, y: currentScale })
    this.stage.position(currentPos)

    return dataUrl
  }

  async getTransformedFullCanvas() {
    if (!this.currentImage) return null
    const originalAttrs = {
      x: this.currentImage.x(),
      y: this.currentImage.y(),
      scaleX: this.currentImage.scaleX(),
      scaleY: this.currentImage.scaleY(),
      rotation: this.currentImage.rotation(),
      offsetX: this.currentImage.offsetX(),
      offsetY: this.currentImage.offsetY()
    }

    const rotation = this.currentImage ? this.currentImage.rotation() : 0
    const rad = (rotation * Math.PI) / 180

    const imgEl = this._getImageElement()
    if (!imgEl) return null
    const imgWidthSrc = imgEl.width
    const imgHeightSrc = imgEl.height

    const rotatedW = Math.round(Math.abs(imgWidthSrc * Math.cos(rad)) + Math.abs(imgHeightSrc * Math.sin(rad)))
    const rotatedH = Math.round(Math.abs(imgWidthSrc * Math.sin(rad)) + Math.abs(imgHeightSrc * Math.cos(rad)))

    // Preserve stage transform and temporarily reset it so exported canvas is independent
    const stageScale = this.stage.scaleX()
    const stagePos = this.stage.position()

    // Render image at scale 1 with rotation applied via image attrs
    this.stage.scale({ x: 1, y: 1 })
    this.stage.position({ x: 0, y: 0 })

    this.currentImage.setAttrs({ scaleX: 1, scaleY: 1, x: rotatedW / 2, y: rotatedH / 2, offsetX: imgWidthSrc / 2, offsetY: imgHeightSrc / 2, rotation })

    const canvas = this.imageLayer.toCanvas({ x: 0, y: 0, width: rotatedW, height: rotatedH, pixelRatio: 1 })

    // Attach helpful metadata so callers can map original-image pixels
    try {
      ;(canvas as any)._meta = { srcW, srcH, rotatedW, rotatedH }
    } catch (e) {}

    // Restore original attributes and stage transform
    this.currentImage.setAttrs(originalAttrs)
    this.stage.scale({ x: stageScale, y: stageScale })
    this.stage.position(stagePos)
    this.imageLayer.batchDraw()

    return canvas
  }

  async getTransformedOriginalCanvas() {
    if (!this.currentImage) return null
    // originalDimensions holds the target "original" pixel size
    const origW = Math.round(this.originalDimensions.width || 0)
    const origH = Math.round(this.originalDimensions.height || 0)
    if (!origW || !origH) return null

    const originalAttrs = {
      x: this.currentImage.x(),
      y: this.currentImage.y(),
      scaleX: this.currentImage.scaleX(),
      scaleY: this.currentImage.scaleY(),
      rotation: this.currentImage.rotation(),
      offsetX: this.currentImage.offsetX(),
      offsetY: this.currentImage.offsetY()
    }

    const rotation = this.currentImage ? this.currentImage.rotation() : 0
    const rad = (rotation * Math.PI) / 180

    const imgEl = this._getImageElement()
    if (!imgEl) return null
    const srcW = imgEl.width
    const srcH = imgEl.height
    if (!srcW || !srcH) return null

    // scale factor to render the Konva image at the original pixel dimensions
    const origScaleX = origW / srcW
    const origScaleY = origH / srcH

    const rotatedW = Math.round(Math.abs(origW * Math.cos(rad)) + Math.abs(origH * Math.sin(rad)))
    const rotatedH = Math.round(Math.abs(origW * Math.sin(rad)) + Math.abs(origH * Math.cos(rad)))

    // Preserve stage transform and temporarily reset it so exported canvas is independent
    const stageScale = this.stage.scaleX()
    const stagePos = this.stage.position()

    this.stage.scale({ x: 1, y: 1 })
    this.stage.position({ x: 0, y: 0 })

    // Set image attributes so Konva draws the node at the requested original pixel size
    this.currentImage.setAttrs({
      scaleX: origScaleX,
      scaleY: origScaleY,
      x: rotatedW / 2,
      y: rotatedH / 2,
      offsetX: srcW / 2,
      offsetY: srcH / 2,
      rotation
    })

    const canvas = this.imageLayer.toCanvas({ x: 0, y: 0, width: rotatedW, height: rotatedH, pixelRatio: 1 })

    // Restore original attributes and stage transform
    this.currentImage.setAttrs(originalAttrs)
    this.stage.scale({ x: stageScale, y: stageScale })
    this.stage.position(stagePos)
    this.imageLayer.batchDraw()

    return canvas
  }

  async exportCropBoxFromOriginal(options: { format?: string; quality?: number; previewMaxWidth?: number } = {}) {
    const { format = 'png', quality = 1, previewMaxWidth } = options

    // Yield one animation frame to allow the UI to render loading indicators
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

    const originalCrops = this.getCropBoxesInfoForOriginal()
    console.debug('exportCropBoxFromOriginal: originalCrops:', originalCrops)

    // null = engine not ready, [] = no crops exist (both are valid reasons to skip)
    if (originalCrops === null) {
      console.warn('exportCropBoxFromOriginal: transform not ready yet')
      return null
    }
    
    if (originalCrops.length === 0) {
      console.warn('exportCropBoxFromOriginal: no crop boxes available (user has deleted all)')
      return null
    }
    const crop = originalCrops[0]
    // Use a canvas rendered at the original image pixel dimensions with all transforms applied
    const fullCanvas = await this.getTransformedOriginalCanvas()
    if (!fullCanvas) {
      console.warn('exportCropBoxFromOriginal: getTransformedOriginalCanvas returned null', { originalDimensions: this.originalDimensions })
      return null
    }

    const cropCanvas = document.createElement('canvas')
    let targetW = Math.round(crop.bbox.w)
    let targetH = Math.round(crop.bbox.h)

    // If caller requests a maximum preview width, scale down preserving aspect
    if (previewMaxWidth && targetW > previewMaxWidth) {
      const scale = previewMaxWidth / targetW
      targetW = Math.round(targetW * scale)
      targetH = Math.round(targetH * scale)
    }

    cropCanvas.width = targetW
    cropCanvas.height = targetH
    const ctx = cropCanvas.getContext('2d')
    if (ctx) {
        // Compute source coordinates in the transformed canvas coordinate space.
        // Prefer metadata from the rendered canvas which encodes how the
        // original image was centered/offset when rendering the rotated canvas.
        // Prefer engine-derived offsets. The engine computes `offsetX/offsetY`
        // in `getCropBoxesInfoForOriginal()` using the Konva node geometry.
        // Relying on a stored canvas `_meta` has proven fragile and can yield
        // incorrect base offsets; use the offsets returned with each crop.
      const cropBoxX = crop.bbox.x + (crop.offsetX || 0)
      const cropBoxY = crop.bbox.y + (crop.offsetY || 0)
      const cropboxW = crop.bbox.w;
      const cropboxH = crop.bbox.h;

      try {
        // Ensure we don't request pixels outside the source canvas
        const srcW = (fullCanvas as HTMLCanvasElement).width;
        const srcH = (fullCanvas as HTMLCanvasElement).height;

        const srcLeft = Math.max(0, Math.floor(cropBoxX));
        const srcTop = Math.max(0, Math.floor(cropBoxY));
        const srcRight = Math.min(srcW, Math.ceil(cropBoxX + cropboxW));
        const srcBottom = Math.min(srcH, Math.ceil(cropBoxY + cropboxH));

        const clampedW = Math.max(0, srcRight - srcLeft);
        const clampedH = Math.max(0, srcBottom - srcTop);

          if (clampedW !== Math.round(cropboxW) || clampedH !== Math.round(cropboxH) || srcLeft !== Math.floor(cropBoxX) || srcTop !== Math.floor(cropBoxY)) {
            console.warn('exportCropBoxFromOriginal: clamping crop rect to canvas bounds', { cropBoxX, cropBoxY, cropboxW, cropboxH, srcW, srcH, clampedW, clampedH, srcLeft, srcTop });
          }

          console.debug('exportCropBoxFromOriginal: final src rect', { srcLeft, srcTop, clampedW, clampedH, srcW, srcH })

        // If clamped size <= 0, nothing to draw
        if (clampedW <= 0 || clampedH <= 0) {
          console.warn('exportCropBoxFromOriginal: clamped crop has non-positive area', { clampedW, clampedH });
          return null
        }

        // Adjust target dimensions proportionally if clamped differs
        const drawTargetW = Math.round((clampedW / cropboxW) * targetW) || 1;
        const drawTargetH = Math.round((clampedH / cropboxH) * targetH) || 1;

        console.debug('exportCropBoxFromOriginal: drawing image with params', { cropBoxX: srcLeft, cropBoxY: srcTop, cropboxW: clampedW, cropboxH: clampedH, targetW: drawTargetW, targetH: drawTargetH })

        ctx.drawImage(fullCanvas as HTMLCanvasElement, srcLeft, srcTop, clampedW, clampedH, 0, 0, drawTargetW, drawTargetH)
      } catch (err) {
        console.error('exportCropBoxFromOriginal: drawImage failed', err)
        return null
      }
    } else {
      console.warn('exportCropBoxFromOriginal: Failed to get 2D context for crop canvas')
      return null
    }

    // Prefer toBlob which is asynchronous and avoids creating a large
    // base64 string in memory. Return the Blob to the caller so it can
    // create an object URL or otherwise handle the binary data.
    const blob: Blob | null = await new Promise(resolve => {
      try {
        cropCanvas.toBlob((b) => resolve(b), `image/${format}`, quality)
      } catch (err) {
        console.warn('toBlob failed, falling back to toDataURL', err)
        const dataUrl = cropCanvas.toDataURL(`image/${format}`, quality)
        // convert dataUrl to blob synchronously via fetch
        fetch(dataUrl).then(r => r.blob()).then(b => resolve(b)).catch(() => resolve(null))
      }
    })

    if (!blob) return null

    const ret = {
      blob: blob,
      width: crop.bbox.w,
      height: crop.bbox.h
    }
    try { console.debug('exportCropBoxFromOriginal: returning blob', { size: blob.size, width: ret.width, height: ret.height }) } catch (e) {}
    return ret
  }

  getImageUrl() {
    if (!this.currentImage || !this.currentImage.image()) return null
    const el = this._getImageElement()
    return el?.src ?? null
  }

  private _getImageElement(): HTMLImageElement | null {
    const img = this.currentImage?.image()
    if (!img) return null
    // If the underlying image is an HTMLImageElement, return it
    if ((img as HTMLImageElement).src !== undefined) return img as HTMLImageElement
    return null
  }

  getRotation() {
    return this.currentImage ? this.currentImage.rotation() : 0
  }

  getFilters() {
    if (!this.currentImage) return { brightness: 0, contrast: 0 }

    return { brightness: this.currentImage.brightness() || 0, contrast: (this.currentImage.contrast() || 0) / 100 }
  }

  applyBrightnessContrast() {
    if (this.imageLayer) {
      this.imageLayer.batchDraw()
    }
  }

  fitToContainer(maxWidth = 1200, maxHeight = 800) {
    if (!this.currentImage) return

    const scale = Math.min(maxWidth / this.currentImage.width(), maxHeight / this.currentImage.height(), 1)

    this.stage.width(this.currentImage.width() * scale)
    this.stage.height(this.currentImage.height() * scale)
    this.stage.batchDraw()
  }

  on(event: string, callback: (...args: any[]) => void) {
    if (!this.listeners.has(event)) this.listeners.set(event, [])
    this.listeners.get(event)!.push(callback)
  }

  off(event: string, callback: (...args: any[]) => void) {
    if (this.listeners.has(event)) {
      const callbacks = this.listeners.get(event)!
      const index = callbacks.indexOf(callback)
      if (index > -1) callbacks.splice(index, 1)
    }
  }

  destroy() {
    this.stage.destroy()
    this.listeners.clear()
  }

  applyRotation(angle: number) {
    if (!this.currentImage) return

    const centerX = (this.currentImage.width() * this.currentImage.scaleX()) / 2
    const centerY = (this.currentImage.height() * this.currentImage.scaleY()) / 2

    this.currentImage.rotation(angle)
    this.currentImage.offsetX(this.currentImage.width() / 2)
    this.currentImage.offsetY(this.currentImage.height() / 2)
    this.currentImage.x(centerX)
    this.currentImage.y(centerY)

    this.imageLayer.batchDraw()
  }

  applyFilters(options: { brightness?: number; contrast?: number } = {}) {
    if (!this.currentImage) return

    const { brightness = 0, contrast = 0 } = options

    // Build filter list depending on requested adjustments
    const filters: any[] = []

    if (Math.abs(brightness) > 0.01) {
      filters.push(Konva.Filters.Brighten)
      this.currentImage.brightness(brightness)
    }

    if (Math.abs(contrast) > 0.01) {
      filters.push(Konva.Filters.Contrast)
      // Konva contrast filter expects roughly -100..100 range
      this.currentImage.contrast(contrast * 100)
    }

    // Apply filters to node (empty array clears filters)
    // Note: image was cached when loaded; avoid re-caching here to prevent
    // heavy synchronous work on every input event.
    this.currentImage.filters(filters)
    this.imageLayer.batchDraw()
  }

  _activateCropTool() {
    this.addCropBox({ x: this.stage.width() / 4, y: this.stage.height() / 4, width: this.stage.width() / 2, height: this.stage.height() / 2 })
  }

  _setupEvents() {
    this.stage.on('click tap', (e: any) => {
      if (e.target === this.stage || e.target === this.imageLayer || e.target === this.currentImage) {
        this.transformer.nodes([])
        this.cropLayer.batchDraw()
      }
    })

    this.stage.on('mousedown touchstart', (e: any) => {
      if (e.target.hasName && e.target.hasName('cropBox')) {
        this.transformer.nodes([e.target])
        this.transformer.forceUpdate()
        this.cropLayer.batchDraw()
      }
    })

    document.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Delete' || e.key === 'Backspace') {
        const target = e.target as HTMLElement
        if (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA') {
          this.deleteSelected()
        }
      }
    })
  }

  _setupZoomPan() {
    this.stage.on('wheel', (e: any) => {
      e.evt.preventDefault()

      if (Math.abs(e.evt.deltaX) > Math.abs(e.evt.deltaY)) {
        const newPos = { x: this.stage.x() - e.evt.deltaX, y: this.stage.y() - e.evt.deltaY }
        this.stage.position(this._constrainPan(newPos))
        this.stage.batchDraw()
        return
      }

      const oldScale = this.stage.scaleX()
      const pointer = this.stage.getPointerPosition()
      if (!pointer) return

      const scaleBy = 1.05
      const direction = e.evt.deltaY > 0 ? -1 : 1

      let newScale = direction > 0 ? oldScale * scaleBy : oldScale / scaleBy
      newScale = Math.max(this.minZoomScale, Math.min(5, newScale))

      this._zoomToPoint(pointer, newScale)
      this._emit('zoomChanged', { zoom: newScale })
    })

    this.stage.on('mousedown', (e: any) => {
      const evt = e.evt
      if (evt.button === 0 && (e.target === this.stage || e.target === this.imageLayer || e.target === this.currentImage)) {
        this.isPanning = true
        this.stage.container().style.cursor = 'grab'
        this.lastPosX = evt.clientX
        this.lastPosY = evt.clientY
        evt.preventDefault()
      }
    })

    this.stage.on('mousemove', (e: any) => {
      if (!this.isPanning) return

      const evt = e.evt
      const dx = evt.clientX - this.lastPosX
      const dy = evt.clientY - this.lastPosY

      const newPos = { x: this.stage.x() + dx, y: this.stage.y() + dy }

      this.stage.position(this._constrainPan(newPos))
      this.stage.batchDraw()

      this.lastPosX = evt.clientX
      this.lastPosY = evt.clientY
      this.stage.container().style.cursor = 'grabbing'
    })

    this.stage.on('mouseup', () => {
      if (this.isPanning) {
        this.isPanning = false
        this.stage.container().style.cursor = 'default'
      }
    })

    this.stage.on('mouseleave', () => {
      if (this.isPanning) {
        this.isPanning = false
        this.stage.container().style.cursor = 'default'
      }
    })
  }

  _zoomToPoint(point: { x: number; y: number }, newScale: number) {
    const oldScale = this.stage.scaleX()
    const mousePointTo = { x: (point.x - this.stage.x()) / oldScale, y: (point.y - this.stage.y()) / oldScale }

    this.stage.scale({ x: newScale, y: newScale })

    const newPos = { x: point.x - mousePointTo.x * newScale, y: point.y - mousePointTo.y * newScale }

    this.stage.position(this._constrainPan(newPos))
    this.stage.batchDraw()
  }

  _constrainPan(pos: { x: number; y: number }) {
    if (!this.currentImage) return pos

    const scale = this.stage.scaleX()
    const stageWidth = this.stage.width()
    const stageHeight = this.stage.height()

    const imageWidth = this.currentImage.width() * this.currentImage.scaleX() * scale
    const imageHeight = this.currentImage.height() * this.currentImage.scaleY() * scale

    const marginX = imageWidth * 0.2
    const marginY = imageHeight * 0.2

    const minX = stageWidth - imageWidth - marginX
    const maxX = marginX

    const minY = stageHeight - imageHeight - marginY
    const maxY = marginY

    return { x: Math.max(minX, Math.min(maxX, pos.x)), y: Math.max(minY, Math.min(maxY, pos.y)) }
  }

  _emit(event: string, data: any = {}) {
    if (this.listeners.has(event)) {
      this.listeners.get(event)!.forEach(cb => cb(data))
    }
  }
}
