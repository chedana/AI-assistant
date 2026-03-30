export type ChecklistItem = { id: string; label: string };
export type ChecklistCategory = { title: string; items: ChecklistItem[] };

export const VIEWING_CHECKLIST: ChecklistCategory[] = [
  {
    title: "Legal Requirements",
    items: [
      { id: "gas_cert", label: "Gas safety certificate (annual, must be provided before move-in)" },
      { id: "epc", label: "Energy Performance Certificate (minimum E rating)" },
      { id: "electrical", label: "Electrical safety report (EICR, valid 5 years)" },
      { id: "smoke_co", label: "Smoke alarms on every floor + CO detector if gas appliances" },
      { id: "deposit_scheme", label: "Ask which deposit protection scheme they use" },
      { id: "how_to_rent", label: "Must receive 'How to Rent' guide before signing" },
      { id: "landlord_identity", label: "Confirm landlord name and contact (not just agent)" },
    ],
  },
  {
    title: "Physical Inspection",
    items: [
      { id: "damp_mould", label: "Check walls, ceilings, window frames for damp or mould" },
      { id: "boiler", label: "Check boiler age and last service date" },
      { id: "water_pressure", label: "Run taps and shower — check water pressure" },
      { id: "windows", label: "Open/close all windows — check seals and locks" },
      { id: "electrics", label: "Test light switches and plug sockets in each room" },
      { id: "broadband", label: "Check mobile signal and ask about broadband speed" },
      { id: "natural_light", label: "Note natural light levels (visit at different times if possible)" },
      { id: "storage", label: "Check cupboard and storage space" },
      { id: "noise", label: "Listen for traffic, neighbours, building noise" },
      { id: "heating", label: "Check radiators in each room — ask about heating bills" },
    ],
  },
  {
    title: "Questions to Ask",
    items: [
      { id: "q_bills", label: "Are any bills included in the rent?" },
      { id: "q_tenancy_length", label: "What is the minimum tenancy length?" },
      { id: "q_rent_increase", label: "How and when can the rent be increased?" },
      { id: "q_maintenance", label: "How are maintenance requests handled? Response time?" },
      { id: "q_inventory", label: "Will there be a professional inventory check-in?" },
      { id: "q_previous_tenant", label: "Why did the previous tenant leave?" },
      { id: "q_neighbours", label: "Any known issues with neighbours?" },
      { id: "q_works", label: "Are there any planned works or developments nearby?" },
    ],
  },
];
