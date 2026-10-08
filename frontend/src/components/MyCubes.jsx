import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { resolveCube, readTextFile } from "@/lib/cube";
import CustomCardsPicker, { toCubeCustoms } from "@/components/CustomCardsPicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Library, Loader2, MoreVertical, Pencil, RefreshCw, Shuffle, Trash2, Download, Upload, ImagePlus } from "lucide-react";
import { toast } from "sonner";

const when = (iso) => {
  try { return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); } catch { return ""; }
};

/** Dashboard "Cubes" tab: the user's saved cube lists. */
export default function MyCubes({ importOpen, setImportOpen, onCount }) {
  const navigate = useNavigate();
  const [cubes, setCubes] = useState(null);
  const [busy, setBusy] = useState(null);          // id of the cube being refreshed
  const [renaming, setRenaming] = useState(null);  // { id, name }
  const [deleting, setDeleting] = useState(null);
  const [customsFor, setCustomsFor] = useState(null); // { id, name, list }

  const load = async () => {
    try {
      const { data } = await api.get("/cubes");
      setCubes(data.cubes || []);
      onCount?.((data.cubes || []).length);
    } catch { setCubes([]); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const refresh = async (cube) => {
    setBusy(cube.id);
    try {
      const { data: full } = await api.get(`/cubes/${cube.id}`);
      const res = await resolveCube({ cubeCobra: cube.cubecobra_id, keep: full.cards });
      if (!res.cards.length) throw new Error("empty");
      const customs = full.cards.filter((c) => c.is_custom);
      const before = new Set(full.cards.filter((c) => !c.is_custom).map((c) => c.name));
      const after = new Set(res.cards.map((c) => c.name));
      const added = [...after].filter((n) => !before.has(n)).length;
      const removed = [...before].filter((n) => !after.has(n)).length;
      await api.put(`/cubes/${cube.id}`, { cards: [...customs, ...res.cards] });
      toast.success(added || removed ? `Updated from CubeCobra: ${added} added, ${removed} removed` : "Already up to date");
      if (res.notFound.length) toast(`${res.notFound.length} card(s) not found and skipped`);
      load();
    } catch { toast.error("Couldn't refresh from CubeCobra"); }
    finally { setBusy(null); }
  };

  const saveName = async () => {
    if (!renaming?.name.trim()) return;
    try { await api.put(`/cubes/${renaming.id}`, { name: renaming.name.trim() }); setRenaming(null); load(); }
    catch { toast.error("Rename failed"); }
  };

  const remove = async () => {
    try { await api.delete(`/cubes/${deleting}`); toast.success("Cube deleted"); setDeleting(null); load(); }
    catch { toast.error("Delete failed"); }
  };

  const downloadList = async (cube) => {
    try {
      const { data } = await api.get(`/cubes/${cube.id}`);
      const text = data.cards.filter((c) => !c.is_custom).map((c) => c.name).join("\n") + "\n";
      const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${cube.name.replace(/[^\w -]+/g, "").trim() || "cube"}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Download failed"); }
  };

  const openCustoms = async (cube) => {
    try {
      const { data } = await api.get(`/cubes/${cube.id}`);
      setCustomsFor({ id: cube.id, name: cube.name, list: data.cards.filter((c) => c.is_custom), rest: data.cards.filter((c) => !c.is_custom) });
    } catch { toast.error("Couldn't open that cube"); }
  };
  const saveCustoms = async () => {
    try {
      await api.put(`/cubes/${customsFor.id}`, { cards: [...toCubeCustoms(customsFor.list), ...customsFor.rest] });
      toast.success("Custom cards saved");
      setCustomsFor(null);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  return (
    <>
      {cubes === null ? (
        <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 text-amber-400 animate-spin" /></div>
      ) : cubes.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-800 py-16 px-6 flex flex-col items-center gap-3 text-center text-slate-500" data-testid="empty-cubes">
          <Library className="w-12 h-12 text-slate-700" />
          <p>No saved cubes yet. Import one from CubeCobra or a list, or tick "Save to My Cubes" when you host a draft.</p>
          <Button data-testid="empty-import-cube" onClick={() => setImportOpen(true)} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold mt-2">
            <Upload className="w-4 h-4 mr-1" /> Import cube
          </Button>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="cube-grid">
          {cubes.map((c) => (
            <div key={c.id} className="rounded-2xl border border-slate-800 bg-slate-900/50 overflow-hidden hover:border-amber-400/40 transition-colors" data-testid={`cube-card-${c.id}`}>
              <div className="h-28 bg-slate-800 relative">
                {c.art ? <img src={c.art} alt="" className="w-full h-full object-cover" /> : <div className="w-full h-full grim-grain" />}
                <div className="absolute inset-0 bg-gradient-to-t from-slate-900 to-transparent" />
                {c.cubecobra_id && <span className="absolute top-2 right-2 text-[10px] px-1.5 py-0.5 rounded bg-black/70 text-slate-300">CubeCobra</span>}
              </div>
              <div className="p-4 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="font-display font-semibold truncate">{c.name}</h3>
                  <p className="text-xs text-slate-500 mt-0.5">{c.card_count} cards{c.custom_count ? ` · ${c.custom_count} custom` : ""} · updated {when(c.updated_at)}</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Button size="sm" data-testid={`host-cube-${c.id}`} onClick={() => navigate(`/draft?cube=${c.id}`)} className="h-8 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
                    <Shuffle className="w-3.5 h-3.5 mr-1" /> Draft
                  </Button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button data-testid={`cube-menu-${c.id}`} className="p-1.5 rounded hover:bg-slate-800 text-slate-400">
                        {busy === c.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <MoreVertical className="w-4 h-4" />}
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="bg-slate-900 border-slate-700 text-slate-200">
                      {c.cubecobra_id && <DropdownMenuItem data-testid={`refresh-cube-${c.id}`} onClick={() => refresh(c)} className="focus:bg-slate-800 cursor-pointer"><RefreshCw className="w-4 h-4 mr-2" /> Refresh from CubeCobra</DropdownMenuItem>}
                      <DropdownMenuItem data-testid={`customs-cube-${c.id}`} onClick={() => openCustoms(c)} className="focus:bg-slate-800 cursor-pointer"><ImagePlus className="w-4 h-4 mr-2" /> Custom cards</DropdownMenuItem>
                      <DropdownMenuItem data-testid={`rename-cube-${c.id}`} onClick={() => setRenaming({ id: c.id, name: c.name })} className="focus:bg-slate-800 cursor-pointer"><Pencil className="w-4 h-4 mr-2" /> Rename</DropdownMenuItem>
                      <DropdownMenuItem data-testid={`download-cube-${c.id}`} onClick={() => downloadList(c)} className="focus:bg-slate-800 cursor-pointer"><Download className="w-4 h-4 mr-2" /> Download list</DropdownMenuItem>
                      <DropdownMenuItem data-testid={`delete-cube-${c.id}`} onClick={() => setDeleting(c.id)} className="focus:bg-slate-800 cursor-pointer text-red-400"><Trash2 className="w-4 h-4 mr-2" /> Delete</DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <ImportCubeDialog open={importOpen} onOpenChange={setImportOpen} onDone={load} />

      <Dialog open={!!renaming} onOpenChange={(o) => !o && setRenaming(null)}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100">
          <DialogHeader><DialogTitle className="font-display">Rename cube</DialogTitle></DialogHeader>
          <Input data-testid="rename-cube-input" value={renaming?.name || ""} onChange={(e) => setRenaming((r) => ({ ...r, name: e.target.value }))} maxLength={120}
            onKeyDown={(e) => e.key === "Enter" && saveName()} className="bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
          <DialogFooter>
            <Button data-testid="rename-cube-save" onClick={saveName} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!customsFor} onOpenChange={(o) => !o && setCustomsFor(null)}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">Custom cards · {customsFor?.name}</DialogTitle>
            <DialogDescription className="text-slate-400">These join every draft of this cube as tokens at the top of the pool.</DialogDescription>
          </DialogHeader>
          {customsFor && <CustomCardsPicker value={customsFor.list} onChange={(list) => setCustomsFor((c) => ({ ...c, list }))} testid="cube-custom" />}
          <DialogFooter>
            <Button data-testid="customs-save" onClick={saveCustoms} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent className="bg-slate-900 border-slate-700 text-slate-100">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this cube?</AlertDialogTitle>
            <AlertDialogDescription className="text-slate-400">Drafts already played with it aren't affected. This can't be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-slate-800 border-slate-700 text-slate-200 hover:bg-slate-700">Cancel</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-delete-cube" onClick={remove} className="bg-red-500 hover:bg-red-600 text-white">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function ImportCubeDialog({ open, onOpenChange, onDone }) {
  const [name, setName] = useState("");
  const [cubeCobra, setCubeCobra] = useState("");
  const [text, setText] = useState("");
  const [customs, setCustoms] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (open) { setName(""); setCubeCobra(""); setText(""); setCustoms([]); } }, [open]);

  const save = async () => {
    if (!cubeCobra.trim() && !text.trim() && !customs.length) { toast.error("Add a CubeCobra link, a list or custom cards"); return; }
    setSaving(true);
    try {
      const res = (cubeCobra.trim() || text.trim()) ? await resolveCube({ cubeCobra, text }) : { cards: [], notFound: [], cubecobraId: null };
      if (!res.cards.length && !customs.length) { toast.error("No cards found in that list"); return; }
      const label = name.trim() || (res.cubecobraId ? `CubeCobra ${res.cubecobraId}` : "My Cube");
      await api.post("/cubes", { name: label, cubecobra_id: res.cubecobraId, cards: [...toCubeCustoms(customs), ...res.cards] });
      toast.success(`Saved "${label}" (${res.cards.length + customs.length} cards)`);
      if (res.notFound.length) toast(`${res.notFound.length} card(s) not found and skipped`);
      onOpenChange(false);
      onDone();
    } catch (e) { toast.error(e.response?.data?.detail || "Import failed"); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="import-cube-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Import a cube</DialogTitle>
          <DialogDescription className="text-slate-400">From CubeCobra, or paste / upload a list. Cards use their original printing.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-1">
          <div>
            <Label className="text-slate-300">Name</Label>
            <Input data-testid="import-cube-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Our Vintage Cube" maxLength={120} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
          </div>
          <div>
            <Label className="text-slate-300">CubeCobra link or ID</Label>
            <Input data-testid="import-cube-cubecobra" value={cubeCobra} onChange={(e) => setCubeCobra(e.target.value)} placeholder="https://cubecobra.com/cube/overview/xxxx" className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
          </div>
          <div className="text-center text-xs text-slate-600">or paste / upload a list (txt, csv, json)</div>
          <div>
            <Textarea data-testid="import-cube-text" value={text} onChange={(e) => setText(e.target.value)} disabled={!!cubeCobra.trim()} placeholder={"Sol Ring\nLightning Bolt\n..."}
              className="min-h-[120px] bg-slate-950 border-slate-700 text-slate-100 font-mono text-sm focus-visible:ring-amber-400 disabled:opacity-40" />
            <label className="inline-flex items-center gap-2 text-sm text-slate-300 mt-2 cursor-pointer hover:text-white">
              <Upload className="w-4 h-4" /> Upload file
              <input type="file" accept=".txt,.csv,.json" className="hidden" data-testid="import-cube-file"
                onChange={async (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) { setText(await readTextFile(f)); if (!name.trim()) setName(f.name.replace(/\.[^.]+$/, "")); } }} />
            </label>
          </div>
          <div>
            <Label className="text-slate-300">Custom cards (optional)</Label>
            <CustomCardsPicker value={customs} onChange={setCustoms} testid="import-custom" />
          </div>
        </div>
        <DialogFooter>
          <Button data-testid="import-cube-save" onClick={save} disabled={saving} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Save cube"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
