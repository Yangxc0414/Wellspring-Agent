import { useEffect, useState } from "react";
import { folderStorage } from "../adapters/folderStorage";
import type { FolderStorageStatus } from "../adapters/folderStorage";

export function useFolderStorage(): FolderStorageStatus {
  const [status, setStatus] = useState(folderStorage.status);
  useEffect(() => folderStorage.subscribe(setStatus), []);
  return status;
}
