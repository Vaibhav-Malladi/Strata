import { saveProfile } from "./api";
import { normalizeDisplayName } from "./utils";

export const submitProfile = (name: string) => saveProfile(normalizeDisplayName(name));
