// Material + bake-profile catalogs for the searchable pickers. Material values are
// sent to the backend, which looks each up in its density table (cortex/bake/physical.py
// MATERIAL_DENSITY — kept in sync with the densities here) to drive real physics.
// Profile values are presets that map to one of the engine's bake archetypes (PROFILE_BASE).
import type { SelOption } from '../SearchSelect'

type MatCat = { group: string; swatch: string; items: [string, string, number][] } // [value, label, kg/m³]

const MATERIAL_CATS: MatCat[] = [
  { group: 'Metal', swatch: '#8a8d92', items: [
    ['aluminum', 'Aluminum', 2700], ['aluminum_alloy', 'Aluminum alloy', 2810], ['steel', 'Steel', 7850],
    ['stainless_steel', 'Stainless steel', 8000], ['cast_iron', 'Cast iron', 7200], ['iron', 'Iron', 7870],
    ['wrought_iron', 'Wrought iron', 7750], ['copper', 'Copper', 8960], ['brass', 'Brass', 8500],
    ['bronze', 'Bronze', 8800], ['gold', 'Gold', 19300], ['silver', 'Silver', 10490], ['lead', 'Lead', 11340],
    ['titanium', 'Titanium', 4500], ['zinc', 'Zinc', 7140], ['nickel', 'Nickel', 8900], ['tin', 'Tin', 7280],
    ['magnesium', 'Magnesium', 1740], ['tungsten', 'Tungsten', 19250], ['chromium', 'Chromium', 7190],
    ['pewter', 'Pewter', 7300], ['platinum', 'Platinum', 21450], ['rusted_steel', 'Rusted steel', 7600] ] },
  { group: 'Wood', swatch: '#6e5a36', items: [
    ['wood', 'Wood', 700], ['oak', 'Oak', 750], ['pine', 'Pine', 500], ['balsa', 'Balsa', 160], ['bamboo', 'Bamboo', 400],
    ['plywood', 'Plywood', 600], ['mahogany', 'Mahogany', 700], ['birch', 'Birch', 670], ['walnut', 'Walnut', 650],
    ['cedar', 'Cedar', 380], ['teak', 'Teak', 650], ['maple', 'Maple', 700], ['ash', 'Ash', 680], ['beech', 'Beech', 720],
    ['spruce', 'Spruce', 450], ['mdf', 'MDF', 750], ['cork', 'Cork', 240], ['driftwood', 'Driftwood', 500],
    ['ebony', 'Ebony', 1100], ['rosewood', 'Rosewood', 850] ] },
  { group: 'Stone', swatch: '#6b6a63', items: [
    ['stone', 'Stone', 2500], ['granite', 'Granite', 2700], ['marble', 'Marble', 2700], ['limestone', 'Limestone', 2600],
    ['sandstone', 'Sandstone', 2300], ['slate', 'Slate', 2800], ['basalt', 'Basalt', 3000], ['quartz', 'Quartz', 2650],
    ['obsidian', 'Obsidian', 2600], ['flint', 'Flint', 2600], ['gneiss', 'Gneiss', 2700], ['pumice', 'Pumice', 640] ] },
  { group: 'Masonry', swatch: '#7a6a5a', items: [
    ['concrete', 'Concrete', 2400], ['brick', 'Brick', 1900], ['plaster', 'Plaster', 1200], ['mortar', 'Mortar', 2200],
    ['terracotta', 'Terracotta', 2000], ['adobe', 'Adobe', 1600], ['cinderblock', 'Cinderblock', 1350],
    ['stucco', 'Stucco', 1850], ['asphalt', 'Asphalt', 2240] ] },
  { group: 'Glass / Ceramic', swatch: '#5b6b6b', items: [
    ['glass', 'Glass', 2500], ['tempered_glass', 'Tempered glass', 2500], ['porcelain', 'Porcelain', 2400],
    ['ceramic', 'Ceramic', 2300], ['clay', 'Clay', 1900], ['stoneware', 'Stoneware', 2300], ['earthenware', 'Earthenware', 2100],
    ['enamel', 'Enamel', 2400] ] },
  { group: 'Plastic', swatch: '#585866', items: [
    ['plastic', 'Plastic', 1100], ['abs', 'ABS', 1050], ['pvc', 'PVC', 1400], ['nylon', 'Nylon', 1150],
    ['polycarbonate', 'Polycarbonate', 1200], ['acrylic', 'Acrylic', 1180], ['polyethylene', 'Polyethylene', 950],
    ['polypropylene', 'Polypropylene', 905], ['polystyrene', 'Polystyrene', 1040], ['resin', 'Resin', 1200],
    ['epoxy', 'Epoxy', 1150], ['bakelite', 'Bakelite', 1300], ['melamine', 'Melamine', 1500], ['teflon', 'Teflon (PTFE)', 2200] ] },
  { group: 'Rubber / Foam', swatch: '#4a4a52', items: [
    ['rubber', 'Rubber', 1100], ['silicone', 'Silicone', 1100], ['neoprene', 'Neoprene', 1230], ['foam', 'Foam', 50],
    ['eva_foam', 'EVA foam', 90], ['latex', 'Latex', 920], ['vinyl', 'Vinyl', 1300], ['styrofoam', 'Styrofoam', 30] ] },
  { group: 'Fabric', swatch: '#6a5a48', items: [
    ['fabric', 'Fabric', 300], ['cotton', 'Cotton', 400], ['wool', 'Wool', 350], ['leather', 'Leather', 900],
    ['felt', 'Felt', 300], ['canvas', 'Canvas', 450], ['denim', 'Denim', 480], ['silk', 'Silk', 350],
    ['burlap', 'Burlap', 320], ['velvet', 'Velvet', 400], ['suede', 'Suede', 850] ] },
  { group: 'Organic', swatch: '#7a6a4a', items: [
    ['paper', 'Paper', 800], ['cardboard', 'Cardboard', 700], ['bone', 'Bone', 1800], ['ivory', 'Ivory', 1850],
    ['wax', 'Wax', 900], ['charcoal', 'Charcoal', 400], ['horn', 'Horn', 1300], ['shell', 'Shell', 2700],
    ['coral', 'Coral', 1500], ['chitin', 'Chitin', 1300], ['hide', 'Hide', 950] ] },
  { group: 'Composite', swatch: '#5a6a6a', items: [
    ['carbon_fiber', 'Carbon fiber', 1600], ['fiberglass', 'Fiberglass', 1900], ['kevlar', 'Kevlar', 1440],
    ['particleboard', 'Particleboard', 700], ['laminate', 'Laminate', 1350], ['gypsum', 'Gypsum board', 800] ] },
  { group: 'Earth', swatch: '#5a4a3a', items: [
    ['sand', 'Sand', 1600], ['gravel', 'Gravel', 1700], ['dirt', 'Dirt', 1300], ['soil', 'Soil', 1300],
    ['mud', 'Mud', 1800], ['peat', 'Peat', 400] ] },
  { group: 'Liquid / Ice', swatch: '#3a5a6a', items: [
    ['water', 'Water', 1000], ['ice', 'Ice', 917], ['snow', 'Snow', 250], ['oil', 'Oil', 900] ] },
  { group: 'Precious / Gem', swatch: '#6a7a8a', items: [
    ['diamond', 'Diamond', 3500], ['ruby', 'Ruby', 4000], ['sapphire', 'Sapphire', 4000], ['emerald', 'Emerald', 2760],
    ['amber', 'Amber', 1060], ['jade', 'Jade', 3300], ['amethyst', 'Amethyst', 2650] ] },
]

export const MATERIAL_OPTIONS: SelOption[] = MATERIAL_CATS.flatMap((c) =>
  c.items.map(([value, label, density]): SelOption => ({ value, label, group: c.group, swatch: c.swatch, hint: `${density} kg/m³` })))

export const MATERIAL_SWATCH: Record<string, string> = Object.fromEntries(
  MATERIAL_CATS.flatMap((c) => c.items.map(([value]) => [value, c.swatch])))

// ---- bake profiles: rich presets that each map to one engine archetype ----
type ProfCat = { group: string; base: string; items: [string, string][] }

const PROFILE_CATS: ProfCat[] = [
  { group: 'Static prop', base: 'rigid_prop', items: [
    ['rigid_prop', 'Rigid prop'], ['crate', 'Crate'], ['crate_metal', 'Metal crate'], ['barrel', 'Barrel'],
    ['rock', 'Rock'], ['boulder', 'Boulder'], ['statue', 'Statue'], ['chair', 'Chair'], ['stool', 'Stool'],
    ['table', 'Table'], ['desk', 'Desk'], ['bench', 'Bench'], ['lamp', 'Lamp'], ['vase', 'Vase'], ['pot', 'Pot'],
    ['tool', 'Tool'], ['weapon', 'Weapon'], ['shield', 'Shield'], ['helmet', 'Helmet'], ['debris', 'Debris'],
    ['rubble', 'Rubble'], ['sign', 'Sign'], ['pillar', 'Pillar'], ['column', 'Column'], ['bottle', 'Bottle'],
    ['can', 'Can'], ['book', 'Book'], ['machine_part', 'Machine part'], ['gear', 'Gear'], ['pipe', 'Pipe'],
    ['fence_post', 'Fence post'], ['bucket', 'Bucket'], ['anvil', 'Anvil'], ['cog', 'Cog'], ['idol', 'Idol'] ] },
  { group: 'Articulated', base: 'door', items: [
    ['door', 'Door'], ['door_double', 'Double door'], ['gate', 'Gate'], ['hatch', 'Hatch'], ['window', 'Window'],
    ['shutter', 'Shutter'], ['lid', 'Lid'], ['drawer', 'Drawer'], ['valve', 'Valve'], ['lever', 'Lever'],
    ['locker_door', 'Locker door'], ['trapdoor', 'Trapdoor'], ['portcullis', 'Portcullis'], ['flap', 'Flap'] ] },
  { group: 'Foliage', base: 'tree', items: [
    ['tree', 'Tree'], ['tree_conifer', 'Conifer'], ['tree_palm', 'Palm'], ['tree_dead', 'Dead tree'], ['bush', 'Bush'],
    ['shrub', 'Shrub'], ['hedge', 'Hedge'], ['plant', 'Plant'], ['vine', 'Vine'], ['fern', 'Fern'], ['flower', 'Flower'],
    ['grass_clump', 'Grass clump'], ['cactus', 'Cactus'], ['sapling', 'Sapling'] ] },
  { group: 'Container', base: 'shelf', items: [
    ['shelf', 'Shelf'], ['bookshelf', 'Bookshelf'], ['cabinet', 'Cabinet'], ['rack', 'Rack'], ['cupboard', 'Cupboard'],
    ['pallet', 'Pallet'], ['bin', 'Bin'], ['basket', 'Basket'], ['toolbox', 'Toolbox'], ['wardrobe', 'Wardrobe'],
    ['chest', 'Chest'], ['drawer_unit', 'Drawer unit'], ['display_case', 'Display case'], ['crate_open', 'Open crate'] ] },
]

export const PROFILE_OPTIONS: SelOption[] = PROFILE_CATS.flatMap((c) =>
  c.items.map(([value, label]): SelOption => ({ value, label, group: c.group })))

// preset → engine archetype (what actually gets baked)
export const PROFILE_BASE: Record<string, string> = Object.fromEntries(
  PROFILE_CATS.flatMap((c) => c.items.map(([value]) => [value, c.base])))
