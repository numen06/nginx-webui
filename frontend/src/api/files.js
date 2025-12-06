import api from "./index";

const encodePath = (path = "") => {
  if (!path) return "";
  return path
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
};

export const filesApi = {
  // 列出文件
  listFiles(path, version, rootOnly) {
    const params = {};
    if (path) params.path = path;
    if (version) params.version = version;
    if (typeof rootOnly === "boolean") params.root_only = rootOnly;
    return api.get("/files", { params });
  },

  // 上传静态资源包（仅保存，不解压）
  uploadPackage(file) {
    const formData = new FormData();
    formData.append("file", file);
    return api.post("/files/upload-package", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
  },

  // 列出已上传的静态资源包
  listPackages() {
    return api.get("/files/packages");
  },

  // 下载静态资源包
  downloadPackage(filename) {
    return api.get(`/files/packages/download/${encodeURIComponent(filename)}`, {
      responseType: "blob",
    });
  },

  // 删除已上传的静态资源包
  deletePackage(filename) {
    return api.delete(`/files/packages/${encodeURIComponent(filename)}`);
  },

  // 部署静态资源包（使用已上传的文件或新上传的文件）
  deployPackage(filename, file, version, extractToSubdir) {
    const formData = new FormData();
    if (filename) {
      formData.append("filename", filename);
    }
    if (file) {
      formData.append("file", file);
    }
    if (version) {
      formData.append("version", version);
    }
    formData.append("extract_to_subdir", extractToSubdir);
    return api.post("/files/deploy-package", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
  },

  // 从静态文件夹根目录提取资源包（扫描压缩包文件）
  extractPackage(directory, deleteAfterExtract) {
    const formData = new FormData();
    if (directory) {
      formData.append("directory", directory);
    }
    formData.append("delete_after_extract", deleteAfterExtract || false);
    return api.post("/files/extract-package", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
  },

  // 获取文件内容
  getFile(path, version, rootOnly) {
    const params = {};
    if (version) params.version = version;
    if (typeof rootOnly === "boolean") params.root_only = rootOnly;
    return api.get(`/files/${encodePath(path)}`, { params });
  },

  // 上传文件
  uploadFile(path, files, version, rootOnly) {
    const formData = new FormData();
    if (path) {
      formData.append("path", path);
    }
    if (version) {
      formData.append("version", version);
    }
    if (typeof rootOnly === "boolean") {
      formData.append("root_only", rootOnly);
    }
    files.forEach((file) => {
      formData.append("files", file);
    });
    return api.post("/files/upload", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
  },

  // 更新文件
  updateFile(path, content, version, rootOnly) {
    const formData = new FormData();
    formData.append("content", content);
    if (version) {
      formData.append("version", version);
    }
    if (typeof rootOnly === "boolean") {
      formData.append("root_only", rootOnly);
    }
    return api.put(`/files/${encodePath(path)}`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
  },

  // 删除文件
  deleteFile(path, version, rootOnly) {
    const params = {};
    if (version) params.version = version;
    if (typeof rootOnly === "boolean") params.root_only = rootOnly;
    return api.delete(`/files/${encodePath(path)}`, { params });
  },

  // 创建目录
  createDirectory(path, name, version, rootOnly) {
    const formData = new FormData();
    if (path) {
      formData.append("path", path);
    }
    if (version) {
      formData.append("version", version);
    }
    formData.append("name", name);
    if (typeof rootOnly === "boolean") {
      formData.append("root_only", rootOnly);
    }
    return api.post("/files/mkdir", formData);
  },

  // 重命名文件
  renameFile(path, newName, version, rootOnly) {
    const formData = new FormData();
    formData.append("new_name", newName);
    if (version) {
      formData.append("version", version);
    }
    if (typeof rootOnly === "boolean") {
      formData.append("root_only", rootOnly);
    }
    return api.post(`/files/rename/${encodePath(path)}`, formData);
  },

  // 下载文件
  downloadFile(path, version, rootOnly) {
    const params = {};
    if (version) params.version = version;
    if (typeof rootOnly === "boolean") params.root_only = rootOnly;
    return api.get(`/files/download/${encodePath(path)}`, {
      params,
      responseType: "blob",
    });
  },

  // 压缩文件夹
  compressDirectory(path, format, version, rootOnly) {
    const formData = new FormData();
    formData.append("path", path);
    formData.append("format", format || "zip");
    if (version) {
      formData.append("version", version);
    }
    if (typeof rootOnly === "boolean") {
      formData.append("root_only", rootOnly);
    }
    return api.post("/files/compress", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
  },

  // 解压压缩包
  extractArchive(path, extractTo, version, rootOnly) {
    const formData = new FormData();
    formData.append("path", path);
    if (extractTo) {
      formData.append("extract_to", extractTo);
    }
    if (version) {
      formData.append("version", version);
    }
    if (typeof rootOnly === "boolean") {
      formData.append("root_only", rootOnly);
    }
    return api.post("/files/extract", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
  },
};
