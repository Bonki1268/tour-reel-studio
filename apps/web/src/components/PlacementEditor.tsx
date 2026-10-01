"use client";

// B1 擺放：在實景照上拖曳角色（腳底中心）、調整大小與翻轉（spec 0015 R-004）
import { useEffect, useState } from "react";
import { Group, Image as KonvaImage, Layer, Rect, Stage } from "react-konva";
import { characterBox, displaySize, SCALE_MAX, SCALE_MIN, toPixels, toRatio, type Placement } from "@/lib/placement";

const MAX_WIDTH = 300;

function useImage(url: string | null | undefined): HTMLImageElement | null {
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    if (!url) return;
    const img = new window.Image();
    img.onload = () => setImage(img);
    img.onerror = () => setImage(null);
    img.src = url;
    return () => {
      img.onload = null;
      img.onerror = null;
    };
  }, [url]);
  return url ? image : null;
}

type Props = {
  shotNo: number;
  photoUrl: string | null | undefined;
  photoSize: { width: number; height: number };
  cutoutUrl: string | null | undefined;
  placement: Placement;
  onChange: (placement: Placement) => void;
};

export default function PlacementEditor({ shotNo, photoUrl, photoSize, cutoutUrl, placement, onChange }: Props) {
  const photo = useImage(photoUrl);
  const cutout = useImage(cutoutUrl);
  const display = displaySize(photoSize, MAX_WIDTH);
  const aspect = cutout ? cutout.naturalWidth / cutout.naturalHeight : 0.5;
  const box = characterBox(placement, display, aspect);
  const foot = toPixels(placement, display);

  return (
    <figure data-testid={`placement-shot-${shotNo}`} className="placement">
      <Stage width={display.width} height={display.height}>
        <Layer>
          {photo ? (
            <KonvaImage image={photo} width={display.width} height={display.height} />
          ) : (
            <Rect width={display.width} height={display.height} fill="#cfd8cf" />
          )}
          <Group
            x={foot.px}
            y={foot.py}
            draggable
            dragBoundFunc={(pos) => ({
              x: Math.min(display.width, Math.max(0, pos.x)),
              y: Math.min(display.height, Math.max(0, pos.y)),
            })}
            onDragEnd={(e) => onChange({ ...placement, ...toRatio({ px: e.target.x(), py: e.target.y() }, display) })}
          >
            {cutout ? (
              <KonvaImage
                image={cutout}
                width={box.width}
                height={box.height}
                // 翻轉時以腳底中心為軸鏡像
                x={placement.flip ? box.width / 2 : -box.width / 2}
                y={-box.height}
                scaleX={placement.flip ? -1 : 1}
              />
            ) : (
              <Rect x={-box.width / 2} y={-box.height} width={box.width} height={box.height} fill="#555" opacity={0.6} />
            )}
          </Group>
        </Layer>
      </Stage>
      <figcaption>
        <label>
          第 {shotNo} 鏡角色大小
          <input
            type="range"
            min={SCALE_MIN * 100}
            max={SCALE_MAX * 100}
            value={Math.round(placement.scale * 100)}
            onChange={(e) => onChange({ ...placement, scale: Number(e.target.value) / 100 })}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={placement.flip}
            onChange={(e) => onChange({ ...placement, flip: e.target.checked })}
          />
          左右翻轉
        </label>
      </figcaption>
    </figure>
  );
}
