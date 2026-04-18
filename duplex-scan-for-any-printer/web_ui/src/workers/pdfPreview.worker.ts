// Web Worker: pdfPreview.worker.ts
// Runs PDF preview page compositing in a worker using OffscreenCanvas
const PREVIEW_PDF_DPI = 150;
const PREVIEW_MARGIN_POINTS = 10;
const A4_POINTS = { width: 595, height: 842 };

function ptsToPx(points: number, dpi = PREVIEW_PDF_DPI) {
  return Math.round((points * dpi) / 72.0);
}

function determineDocumentSpanClient(imgW: number, imgH: number, pageW: number, pageH: number, margin: number, dpi: number = 300) {
  const halfW = Math.floor(pageW / 2);
  const halfH = Math.floor(pageH / 2);
  const imgWpt = Math.floor((imgW * 72.0) / dpi);
  const imgHpt = Math.floor((imgH * 72.0) / dpi);

  const canFitInQuadrant = (qw: number, qh: number) => imgWpt <= Math.max(0, qw - 2 * margin) && imgHpt <= Math.max(0, qh - 2 * margin);

  if (canFitInQuadrant(halfW, halfH)) return 'single';

  const fullWAvail = Math.max(0, pageW - 2 * margin);
  const halfHAvail = Math.max(0, halfH - 2 * margin);
  if (imgWpt <= fullWAvail && imgHpt <= halfHAvail) return 'half_horizontal';

  const halfWAvail = Math.max(0, halfW - 2 * margin);
  const fullHAvail = Math.max(0, pageH - 2 * margin);
  if (imgWpt <= halfWAvail && imgHpt <= fullHAvail) return 'half_vertical';

  return 'full';
}

function computeDocumentPositionClient(bboxX: number, bboxY: number, bboxW: number, bboxH: number, scanW: number, scanH: number, imgW: number, imgH: number, pageW: number, pageH: number, margin: number, span: string, dpi: number = 300) {
  const imgWpt = Math.floor((imgW * 72.0) / dpi);
  const imgHpt = Math.floor((imgH * 72.0) / dpi);

  const cxNorm = (bboxX + bboxW / 2.0) / scanW;
  const cyNorm = (bboxY + bboxH / 2.0) / scanH;

  const halfW = Math.floor(pageW / 2);
  const halfH = Math.floor(pageH / 2);

  if (span === 'single') {
    let regionX = 0, regionY = 0, regionW = halfW, regionH = halfH;
    if (cxNorm < 0.5 && cyNorm < 0.5) { regionX = 0; regionY = halfH; }
    else if (cxNorm >= 0.5 && cyNorm < 0.5) { regionX = halfW; regionY = halfH; }
    else if (cxNorm < 0.5 && cyNorm >= 0.5) { regionX = 0; regionY = 0; }
    else { regionX = halfW; regionY = 0; }

    const drawX = regionX + margin;
    const drawY = regionY + regionH - margin - imgHpt;
    return { x: drawX, y: drawY, w: imgWpt, h: imgHpt };
  }

  if (span === 'half_horizontal') {
    let regionX = 0, regionY = cyNorm < 0.5 ? halfH : 0, regionW = pageW, regionH = halfH;
    let drawX = regionX + Math.floor((regionW - imgWpt) / 2);
    if (cxNorm < 0.33) drawX = regionX + margin;
    else if (cxNorm > 0.67) drawX = regionX + regionW - margin - imgWpt;
    const drawY = regionY + regionH - margin - imgHpt;
    return { x: drawX, y: drawY, w: imgWpt, h: imgHpt };
  }

  if (span === 'half_vertical') {
    let regionX = cxNorm < 0.5 ? 0 : halfW, regionW = halfW, regionH = pageH, regionY = 0;
    let drawY = regionY + Math.floor((regionH - imgHpt) / 2);
    if (cyNorm < 0.33) drawY = regionY + regionH - margin - imgHpt;
    else if (cyNorm > 0.67) drawY = regionY + margin;
    const drawX = regionX + margin;
    return { x: drawX, y: drawY, w: imgWpt, h: imgHpt };
  }

  return { x: Math.floor((pageW - imgWpt) / 2), y: Math.floor((pageH - imgHpt) / 2), w: imgWpt, h: imgHpt };
}

function layoutDocumentsSmartClient(doc_items: Array<[string, any, HTMLCanvasElement | OffscreenCanvas, number]>, page_w: number, page_h: number, margin: number) {
  if (!doc_items || doc_items.length === 0) return [];
  const pages: Array<Array<[string, [number, number], HTMLCanvasElement | OffscreenCanvas, number]>> = [];
  let current_page: Array<[string, [number, number], HTMLCanvasElement | OffscreenCanvas, number]> = [];
  const quadrantsOccupied: any = { tl: false, tr: false, bl: false, br: false };

  const quadrantPositions: any = {
    tl: [margin, Math.floor(page_h / 2)],
    tr: [Math.floor(page_w / 2) + margin, Math.floor(page_h / 2)],
    bl: [margin, 0],
    br: [Math.floor(page_w / 2) + margin, 0]
  };

  function startNewPage() {
    if (current_page.length) pages.push(current_page);
    current_page = [];
    quadrantsOccupied.tl = quadrantsOccupied.tr = quadrantsOccupied.bl = quadrantsOccupied.br = false;
  }

  function checkAndPlace(required: string[], spanType: string, imgRef: any, dpiRef: number, posFunc: () => [number, number]) {
    const allAvailable = required.every((q) => !quadrantsOccupied[q]);
    if (!allAvailable) startNewPage();
    const [dx, dy] = posFunc();
    current_page.push([spanType, [dx, dy], imgRef, dpiRef]);
    required.forEach((q) => { quadrantsOccupied[q] = true; });
  }

  for (let i = 0; i < doc_items.length; i++) {
    const [span, _pos, img, dpi] = doc_items[i];
    if (span === 'single') {
      if (!quadrantsOccupied.tl) checkAndPlace(['tl'], span, img, dpi, () => quadrantPositions.tl);
      else if (!quadrantsOccupied.tr) checkAndPlace(['tr'], span, img, dpi, () => quadrantPositions.tr);
      else if (!quadrantsOccupied.bl) checkAndPlace(['bl'], span, img, dpi, () => quadrantPositions.bl);
      else if (!quadrantsOccupied.br) checkAndPlace(['br'], span, img, dpi, () => quadrantPositions.br);
      else checkAndPlace(['tl'], span, img, dpi, () => quadrantPositions.tl);
    } else if (span === 'half_horizontal') {
      if (!quadrantsOccupied.tl && !quadrantsOccupied.tr) checkAndPlace(['tl', 'tr'], span, img, dpi, () => quadrantPositions.tl);
      else if (!quadrantsOccupied.bl && !quadrantsOccupied.br) checkAndPlace(['bl', 'br'], span, img, dpi, () => quadrantPositions.bl);
      else checkAndPlace(['tl', 'tr'], span, img, dpi, () => quadrantPositions.tl);
    } else if (span === 'half_vertical') {
      if (!quadrantsOccupied.tl && !quadrantsOccupied.bl) checkAndPlace(['tl', 'bl'], span, img, dpi, () => quadrantPositions.tl);
      else if (!quadrantsOccupied.tr && !quadrantsOccupied.br) checkAndPlace(['tr', 'br'], span, img, dpi, () => quadrantPositions.tr);
      else checkAndPlace(['tl', 'bl'], span, img, dpi, () => quadrantPositions.tl);
    } else {
      startNewPage();
      pages.push([[span, [margin, margin], img, dpi]]);
      startNewPage();
    }
  }

  if (current_page.length) pages.push(current_page);
  return pages;
}

self.addEventListener('message', async (ev: MessageEvent) => {
  const { id, payload } = ev.data || {};
  try {
    // quick ping handler
    if (payload && payload.type === 'ping') {
      try { self.postMessage({ id, pong: true }); } catch (e) {}
      return;
    }
    if (!payload || !payload.type) throw new Error('invalid payload');

    if (payload.type === 'selected') {
      // payload: { blob, bbox, scanW, scanH, exportWidth, exportHeight, imageMeta }
      const blob: Blob = payload.blob;
      const bbox = payload.bbox || { x: 0, y: 0, w: payload.exportWidth || 1, h: payload.exportHeight || 1 };
      const scanW = payload.scanW || 1;
      const scanH = payload.scanH || 1;
      const exportW = payload.exportWidth || (payload.exportWidth === 0 ? 0 : payload.exportWidth) || 0;
      const exportH = payload.exportHeight || 0;
      const metaDpi = (payload.imageMeta && payload.imageMeta.scan_dpi) ? Number(payload.imageMeta.scan_dpi) : 300;

      const imgBitmap = await createImageBitmap(blob);

      const span = determineDocumentSpanClient(exportW || imgBitmap.width, exportH || imgBitmap.height, A4_POINTS.width, A4_POINTS.height, PREVIEW_MARGIN_POINTS, metaDpi);
      const pos = computeDocumentPositionClient((bbox.x || 0), (bbox.y || 0), bbox.w, bbox.h, scanW, scanH, exportW || imgBitmap.width, exportH || imgBitmap.height, A4_POINTS.width, A4_POINTS.height, PREVIEW_MARGIN_POINTS, span, metaDpi);

      const pagePxW = ptsToPx(A4_POINTS.width, PREVIEW_PDF_DPI);
      const pagePxH = ptsToPx(A4_POINTS.height, PREVIEW_PDF_DPI);
      const pageCanvas = new OffscreenCanvas(pagePxW, pagePxH);
      const ctx = pageCanvas.getContext('2d');
      if (ctx) {
        ctx.fillStyle = '#ffffff'; ctx.fillRect(0,0,pagePxW,pagePxH);
        const drawXpx = ptsToPx(pos.x, PREVIEW_PDF_DPI);
        const drawYpx = ptsToPx(pos.y, PREVIEW_PDF_DPI);
        const drawWpx = ptsToPx(pos.w, PREVIEW_PDF_DPI);
        const drawHpx = ptsToPx(pos.h, PREVIEW_PDF_DPI);
        ctx.drawImage(imgBitmap, 0, 0, imgBitmap.width, imgBitmap.height, drawXpx, drawYpx, drawWpx, drawHpx);
      }

      const outBlob = await pageCanvas.convertToBlob({ type: 'image/jpeg', quality: 0.85 });
      // Do not transfer Blob as a transferable; just post it (transferables for Blob are not universally supported)
      self.postMessage({ id, result: { pages: [outBlob] } });
      return;
    }

    if (payload.type === 'project') {
      // payload.images = [{ url, bbox, rotation, deskew_angle, brightness, contrast, scan_dpi }]
      const images = payload.images || [];
      const croppedItems: Array<{ canvas: OffscreenCanvas; bbox: any; scanW: number; scanH: number; width: number; height: number; scanDpi?: number }> = [];

      // Inform main thread we started processing
      try { self.postMessage({ id, progress: 0, message: 'starting project processing', total: images.length }); } catch (e) {}

      for (let i = 0; i < images.length; i++) {
        const m = images[i];
        if (!m.url) continue;
        if (!m.bbox) continue;
        try {
          try { self.postMessage({ id, progress: Math.round((i / images.length) * 100), message: 'processing image', index: i }); } catch (e) {}
          const resp = await fetch(m.url);
          if (!resp.ok) continue;
          const b = await resp.blob();
          const imgBitmap = await createImageBitmap(b);

          // Apply rotation
          const rot = Number(m.rotation || 0) + Number(m.deskew_angle || 0);
          const rad = (rot * Math.PI) / 180;
          const cos = Math.abs(Math.cos(rad));
          const sin = Math.abs(Math.sin(rad));
          const rotW = Math.round(imgBitmap.width * cos + imgBitmap.height * sin);
          const rotH = Math.round(imgBitmap.width * sin + imgBitmap.height * cos);

          const transformed = new OffscreenCanvas(rotW, rotH);
          const tctx = transformed.getContext('2d');
          if (!tctx) continue;
          
          tctx.fillStyle = '#ffffff'; tctx.fillRect(0,0,rotW,rotH);
          tctx.translate(rotW/2, rotH/2);
          tctx.rotate(-rad);
          tctx.drawImage(imgBitmap, -imgBitmap.width/2, -imgBitmap.height/2);

          const offsetX = (rotW - imgBitmap.width) / 2;
          const offsetY = (rotH - imgBitmap.height) / 2;

          // Tuy nhiên, vì rotW/rotH thường được tính bằng chính công thức trên, 
          // nên nếu m.bbox.x bắt đầu từ mép ảnh thực, bạn có thể cần kiểm tra:
          const bx = Math.round(m.bbox.x + (offsetX || 0));
          const by = Math.round(m.bbox.y + (offsetY || 0));

          // const bx = m.bbox.x
          // const by = m.bbox.y;
          const bw = m.bbox.w;
          const bh = m.bbox.h;
          console.log(`Cropping image ${i}: bbox (${m.bbox.x}, ${m.bbox.y}, ${m.bbox.w}, ${m.bbox.h}) adjusted to (${bx}, ${by}, ${bw}, ${bh}) on rotated canvas (${rotW}x${rotH})`);
          const crop = new OffscreenCanvas(bw, bh);
          const cctx = crop.getContext('2d');
          if (!cctx) continue;
          // brightness/contrast approximated by globalAlpha for brightness only (worker environment lacks CSS filters reliably)
          cctx.drawImage(transformed, bx, by, bw, bh, 0, 0, bw, bh);

          croppedItems.push({ canvas: crop, bbox: m.bbox, scanW: imgBitmap.width, scanH: imgBitmap.height, width: bw, height: bh, scanDpi: m.scan_dpi || 300 });
          try { self.postMessage({ id, progress: Math.round(((i+1) / images.length) * 100), message: 'cropped image', index: i }); } catch (e) {}
        } catch (e) {
          // ignore failed images
          try { self.postMessage({ id, message: 'image failed', index: i, error: String(e) }); } catch (e2) {}
          continue;
        }
      }

      // Build doc_items
      const docItems: Array<[string, any, OffscreenCanvas, number]> = [];
      for (const it of croppedItems) {
        const span = determineDocumentSpanClient(it.width, it.height, A4_POINTS.width, A4_POINTS.height, PREVIEW_MARGIN_POINTS, it.scanDpi || 300);
        docItems.push([span, [0,0], it.canvas, it.scanDpi || 300]);
      }

      const packedPages = layoutDocumentsSmartClient(docItems, A4_POINTS.width, A4_POINTS.height, PREVIEW_MARGIN_POINTS);
      const pagePxW = ptsToPx(A4_POINTS.width, PREVIEW_PDF_DPI);
      const pagePxH = ptsToPx(A4_POINTS.height, PREVIEW_PDF_DPI);
      const outPages: Blob[] = [];

      for (let pi = 0; pi < packedPages.length; pi++) {
        const p = packedPages[pi];
        try { self.postMessage({ id, progress: Math.round((pi / packedPages.length) * 100), message: 'compositing page', pageIndex: pi }); } catch (e) {}
        const pageCanvas = new OffscreenCanvas(pagePxW, pagePxH);
        const pctx = pageCanvas.getContext('2d');
        if (!pctx) continue;
        pctx.fillStyle = '#ffffff'; pctx.fillRect(0,0,pagePxW,pagePxH);
        for (const [span, [draw_x_pt, draw_y_pt], imgRef, dpiRef] of p) {
          const imgWpx = (imgRef as any).width || 0;
          const imgHpx = (imgRef as any).height || 0;
          let target_w_pt = 0, target_h_pt = 0;
          if (span === 'single') { target_w_pt = A4_POINTS.width / 2 - 2 * PREVIEW_MARGIN_POINTS; target_h_pt = A4_POINTS.height / 2 - 2 * PREVIEW_MARGIN_POINTS; }
          else if (span === 'half_horizontal') { target_w_pt = A4_POINTS.width - 2 * PREVIEW_MARGIN_POINTS; target_h_pt = A4_POINTS.height / 2 - 2 * PREVIEW_MARGIN_POINTS; }
          else if (span === 'half_vertical') { target_w_pt = A4_POINTS.width / 2 - 2 * PREVIEW_MARGIN_POINTS; target_h_pt = A4_POINTS.height - 2 * PREVIEW_MARGIN_POINTS; }
          else { target_w_pt = A4_POINTS.width - 2 * PREVIEW_MARGIN_POINTS; target_h_pt = A4_POINTS.height - 2 * PREVIEW_MARGIN_POINTS; }

          const imgWpt = Math.floor((imgWpx * 72.0) / dpiRef);
          const imgHpt = Math.floor((imgHpx * 72.0) / dpiRef);
          let finalWpt = imgWpt, finalHpt = imgHpt;
          if (imgWpt > target_w_pt || imgHpt > target_h_pt) {
            const scale = Math.min(target_w_pt / imgWpt, target_h_pt / imgHpt);
            finalWpt = Math.floor(imgWpt * scale);
            finalHpt = Math.floor(imgHpt * scale);
          }

          let final_x_pt = draw_x_pt;
          let final_y_pt = draw_y_pt;
          const Wpt = A4_POINTS.width;
          const Hpt = A4_POINTS.height;
          if (span === 'half_horizontal') {
            final_x_pt = (Wpt - finalWpt) / 2.0;
            final_y_pt = draw_y_pt;
          } else if (span === 'half_vertical') {
            final_y_pt = (Hpt - finalHpt) / 2.0;
            final_x_pt = draw_x_pt;
          } else if (span === 'single') {
            const half_w = Math.floor(Wpt / 2);
            final_x_pt = draw_x_pt + (half_w - 2 * PREVIEW_MARGIN_POINTS - finalWpt) / 2.0;
            final_y_pt = draw_y_pt + (half_w - 2 * PREVIEW_MARGIN_POINTS - finalHpt) / 2.0;
          } else {
            final_x_pt = (Wpt - finalWpt) / 2.0;
            final_y_pt = (Hpt - finalHpt) / 2.0;
          }

          const drawXpx = ptsToPx(final_x_pt, PREVIEW_PDF_DPI);
          const drawYpx = ptsToPx(final_y_pt, PREVIEW_PDF_DPI);
          const drawWpx = ptsToPx(finalWpt, PREVIEW_PDF_DPI);
          const drawHpx = ptsToPx(finalHpt, PREVIEW_PDF_DPI);

          try { pctx.drawImage(imgRef as any, 0, 0, imgWpx, imgHpx, drawXpx, drawYpx, drawWpx, drawHpx); } catch (e) { }
        }
        const blob = await pageCanvas.convertToBlob({ type: 'image/jpeg', quality: 0.8 });
        if (blob) outPages.push(blob);
        try { self.postMessage({ id, progress: Math.round(((pi+1) / packedPages.length) * 100), message: 'page ready', pageIndex: pi }); } catch (e) {}
      }
      // Post blobs back
      self.postMessage({ id, result: { pages: outPages } });
      return;
    }

    throw new Error('unknown payload type');
  } catch (err: any) {
    try { self.postMessage({ id, error: String(err && err.message ? err.message : err) }); } catch (e) {}
  }
});
