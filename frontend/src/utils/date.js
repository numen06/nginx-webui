/**
 * 统一的时间格式化工具
 * 格式：YYYY-MM-DD HH:mm:ss
 */

/**
 * 格式化日期时间为标准格式
 * @param {string|Date} dateString - 日期字符串或 Date 对象
 * @returns {string} 格式化后的日期时间字符串，格式：YYYY-MM-DD HH:mm:ss
 */
export const formatDateTime = (dateString) => {
  if (!dateString) return '-'
  
  let date
  if (dateString instanceof Date) {
    date = dateString
  } else {
    date = new Date(dateString)
  }
  
  if (isNaN(date.getTime())) {
    return dateString // 如果无法解析，返回原始值
  }
  
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

/**
 * 格式化日期（不包含时间）
 * @param {string|Date} dateString - 日期字符串或 Date 对象
 * @returns {string} 格式化后的日期字符串，格式：YYYY-MM-DD
 */
export const formatDate = (dateString) => {
  if (!dateString) return '-'
  
  let date
  if (dateString instanceof Date) {
    date = dateString
  } else {
    date = new Date(dateString)
  }
  
  if (isNaN(date.getTime())) {
    return dateString
  }
  
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  
  return `${year}-${month}-${day}`
}

/**
 * 格式化时间（不包含日期）
 * @param {string|Date} dateString - 日期字符串或 Date 对象
 * @returns {string} 格式化后的时间字符串，格式：HH:mm:ss
 */
export const formatTime = (dateString) => {
  if (!dateString) return '-'
  
  let date
  if (dateString instanceof Date) {
    date = dateString
  } else {
    date = new Date(dateString)
  }
  
  if (isNaN(date.getTime())) {
    return dateString
  }
  
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  
  return `${hours}:${minutes}:${seconds}`
}

