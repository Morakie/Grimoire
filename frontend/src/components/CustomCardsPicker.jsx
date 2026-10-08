import React from "react";
import { Input } from "@/components/ui/input";
import { ImagePlus, X } from "lucide-react";
import { toast } from "sonner";
import { resizeImage, fileBaseName } from "@/lib/cube";

export const MAX_CUSTOM = 30;

/** Upload, rename and remove custom card images. `value` is [{ id, name, image }]. */
export default function CustomCardsPicker({ value, onChange, testid = "custom-card" }) {
  const add = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    const room = MAX_CUSTOM - value.length;
    if (files.length > room) toast(`Only ${Math.max(room, 0)} more custom card(s) fit (${MAX_CUSTOM} max)`);
    const added = [];
    for (const f of files.slice(0, Math.max(room, 0))) {
      try {
        added.push({ id: Math.random().toString(36).slice(2, 10), name: fileBaseName(f) || "Custom card", image: await resizeImage(f) });
      } catch { toast.error(`${f.name} isn't an image`); }
    }
    onChange([...value, ...added]);
  };
  const rename = (id, name) => onChange(value.map((c) => (c.id === id ? { ...c, name } : c)));
  const remove = (id) => onChange(value.filter((c) => c.id !== id));

  return (
    <div>
      {value.length > 0 && (
        <div className="mt-3 grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-6 gap-3">
          {value.map((c) => (
            <div key={c.id} className="relative" data-testid={`${testid}-${c.id}`}>
              <div className="aspect-[0.716] rounded-lg overflow-hidden border border-slate-700 bg-slate-800">
                <img src={c.image} alt={c.name} className="w-full h-full object-cover" />
              </div>
              <button type="button" onClick={() => remove(c.id)} title="Remove" data-testid={`custom-remove-${c.id}`}
                className="absolute top-1 right-1 w-6 h-6 rounded bg-black/80 text-white hover:bg-red-500 flex items-center justify-center"><X className="w-3.5 h-3.5" /></button>
              <Input value={c.name} onChange={(e) => rename(c.id, e.target.value)} maxLength={80} aria-label="Card name"
                className="mt-1.5 h-8 text-xs bg-slate-950 border-slate-700 text-slate-100" />
            </div>
          ))}
        </div>
      )}
      <label className="mt-3 inline-flex items-center gap-2 text-sm px-3 h-9 rounded-md border border-slate-700 bg-slate-950 text-slate-300 cursor-pointer hover:text-white hover:border-slate-600">
        <ImagePlus className="w-4 h-4" /> Add card images
        <input type="file" accept="image/*" multiple onChange={add} className="hidden" data-testid={`${testid}-file`} />
      </label>
    </div>
  );
}

/** Custom cards in the shape drafts and saved cubes store them. */
export const toCubeCustoms = (list) => list.map((c) => ({
  id: c.id.startsWith("custom-") ? c.id : `custom-${c.id}`,
  name: c.name.trim() || "Custom card", image: c.image, is_custom: true,
}));
