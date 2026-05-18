<template>
  <section class="surface list-page">
    <div class="toolbar">
      <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap">
        <el-button type="primary" :icon="Plus" @click="openCreate">新增代理</el-button>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button :icon="Setting" @click="openGlobalConfig">全局配置</el-button>
        <el-button type="success" :icon="Switch" :loading="reloading" title="重新生成全部智能代理配置并热重载 Mihomo" @click="confirmReloadRuntime">重新应用到 Mihomo</el-button>
        <el-button :icon="DataAnalysis" :loading="reloading" title="预览即将写入 Mihomo 的 Runtime 配置" @click="reloadRuntime(false)">预览配置</el-button>
        <el-button :icon="Lock" :loading="enforcingAccess" @click="enforceAccess">访问检查</el-button>
      </div>
    </div>
    <el-descriptions :column="4" border style="margin-bottom: 14px">
      <el-descriptions-item label="Mihomo">
        <el-tag :type="coreStatus.available ? 'success' : 'danger'">{{ coreStatusText(coreStatus.available) }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="版本">{{ coreStatus.version || '-' }}</el-descriptions-item>
      <el-descriptions-item label="连接">{{ coreStatus.active_connections }}</el-descriptions-item>
      <el-descriptions-item label="速率">{{ formatRate(coreStatus.upload_speed) }} / {{ formatRate(coreStatus.download_speed) }}</el-descriptions-item>
      <el-descriptions-item label="上传">{{ formatBytes(coreStatus.upload_total) }}</el-descriptions-item>
      <el-descriptions-item label="下载">{{ formatBytes(coreStatus.download_total) }}</el-descriptions-item>
      <el-descriptions-item label="内存">{{ coreStatus.memory ? formatBytes(coreStatus.memory) : '-' }}</el-descriptions-item>
      <el-descriptions-item label="API">{{ coreStatus.api_url || '-' }}</el-descriptions-item>
    </el-descriptions>
    <el-table class="list-table" :data="items" stripe height="100%" empty-text="暂无代理服务">
      <el-table-column prop="name" label="代理名称" min-width="160" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">{{ typeLabel(row.proxy_type) }}</template>
      </el-table-column>
      <el-table-column label="策略" width="120">
        <template #default="{ row }">{{ strategyLabel(row.strategy, row.stability_priority) }}</template>
      </el-table-column>
      <el-table-column label="代理地址" min-width="360">
        <template #default="{ row }">
          <div class="endpoint-list">
            <div v-for="endpoint in endpointOptions(row)" :key="endpoint.scheme" class="endpoint-row">
              <el-tag class="endpoint-tag" size="small" effect="plain">{{ endpoint.label }}</el-tag>
              <el-tooltip :content="endpoint.url" placement="top">
                <span class="endpoint-text">{{ endpoint.url }}</span>
              </el-tooltip>
              <el-button
                class="endpoint-copy"
                :icon="DocumentCopy"
                circle
                size="small"
                :title="`复制${endpoint.label}地址`"
                @click="copy(endpoint.url)"
              />
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="candidate_nodes" label="候选节点" width="100" />
      <el-table-column label="当前节点" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.current_node || '-' }}</template>
      </el-table-column>
      <el-table-column label="切换" width="90">
        <template #default="{ row }">
          <el-button link type="primary" title="查看节点切换历史" @click="showSwitchLogs(row)">
            {{ row.switch_count }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column width="110">
        <template #header>
          <span class="label-with-help">
            状态
            <el-popover placement="top" width="360" trigger="hover">
              <template #reference>
                <span class="help-icon" title="查看状态说明">?</span>
              </template>
              <div class="strategy-help">
                <div v-for="item in runtimeStatusOptions" :key="item.value" class="strategy-help-item">
                  <strong>{{ item.label }}</strong>
                  <span>{{ item.description }}</span>
                </div>
              </div>
            </el-popover>
          </span>
        </template>
        <template #default="{ row }">
          <el-tag :type="runtimeStatusTag(row)">{{ runtimeStatusLabel(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="应用" width="110">
        <template #default="{ row }">
          <el-tooltip :content="applyStatusReason(row)" placement="top">
            <el-tag :type="applyStatusType(row)">{{ applyStatusLabel(row) }}</el-tag>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <el-space :size="6" wrap>
            <el-button link type="primary" :icon="Edit" title="编辑代理" @click="openEdit(row)">编辑</el-button>
            <el-button
              link
              type="primary"
              :icon="DataAnalysis"
              title="查看运行状态并执行健康检测"
              @click="openDiagnosis(row)"
            >
              诊断
            </el-button>
            <el-button
              v-if="row.enabled"
              link
              type="warning"
              :icon="VideoPause"
              title="停止代理"
              @click="stopProxy(row)"
            >
              停用
            </el-button>
            <el-button
              v-else
              link
              type="success"
              :icon="VideoPlay"
              title="启动代理"
              @click="startProxy(row)"
            >
              启用
            </el-button>
            <el-button link type="danger" :icon="Delete" title="删除代理" @click="deleteProxy(row)">删除</el-button>
          </el-space>
        </template>
      </el-table-column>
    </el-table>
  </section>

  <el-dialog v-model="dialogVisible" :title="editingId ? '编辑代理' : '新增代理'" width="980px">
    <el-form label-position="top" class="smart-proxy-form">
      <el-tabs v-model="activeDialogTab" class="proxy-dialog-tabs">
        <el-tab-pane label="基础配置" name="basic">
          <el-radio-group
            v-if="!editingId"
            v-model="creationMode"
            class="smart-proxy-mode"
            @change="onCreationModeChange"
          >
            <el-radio-button label="quick">快速模板</el-radio-button>
            <el-radio-button label="advanced">高级编排</el-radio-button>
            <el-radio-button label="manual">手动选节点</el-radio-button>
          </el-radio-group>

          <div v-if="!editingId && creationMode === 'quick'" class="preset-grid">
            <button
              v-for="preset in metadata.presets"
              :key="preset.key"
              type="button"
              class="preset-card"
              :class="{ active: selectedPresetKey === preset.key }"
              @click="applyPreset(preset)"
            >
              <span class="preset-title">{{ preset.name }}</span>
              <span class="preset-desc">{{ preset.description }}</span>
              <span class="preset-meta">
                <el-tag size="small" effect="plain">{{ strategyLabel(preset.strategy) }}</el-tag>
                <el-tag size="small" effect="plain">{{ scenarioLabel(preset.scenario) }}</el-tag>
              </span>
            </button>
          </div>

          <div class="form-grid">
            <el-form-item label="代理名称" required>
              <el-input v-model="form.name" placeholder="例如：ChatGPT 专线" />
            </el-form-item>
            <el-form-item label="使用场景" required>
              <el-select v-model="form.scenario">
                <el-option label="通用" value="general" />
                <el-option label="AI / OpenAI" value="ai" />
                <el-option label="流媒体" value="streaming" />
                <el-option label="低延迟" value="latency" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="描述">
            <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选" />
          </el-form-item>
          <div class="form-grid">
            <el-form-item label="代理类型" required>
              <el-select v-model="form.proxy_type">
                <el-option label="HTTP / HTTPS CONNECT" value="http" />
                <el-option label="SOCKS5" value="socks" />
                <el-option label="混合代理" value="mixed" />
              </el-select>
            </el-form-item>
            <el-form-item label="监听地址" required>
              <el-input v-model="form.listen_host" placeholder="127.0.0.1 或 0.0.0.0" />
            </el-form-item>
            <el-form-item label="监听端口" required>
              <el-input-number
                v-model="form.port"
                :min="globalConfig.smart_proxy_port_start"
                :max="globalConfig.smart_proxy_port_end"
                controls-position="right"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="启用代理" class="switch-form-item">
              <el-switch v-model="form.enabled" active-text="启用" inactive-text="停用" inline-prompt />
            </el-form-item>
          </div>
          <div class="form-grid">
            <el-form-item label="节点来源" required>
              <el-select v-model="form.source_mode" @change="onSourceModeChange">
                <el-option label="所有节点" value="all" />
                <el-option label="指定订阅" value="subscription" />
                <el-option label="指定国家" value="country" />
                <el-option label="指定标签" value="tag" />
                <el-option label="指定节点" value="manual" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.source_mode === 'country'" label="国家/地区" required>
              <el-select
                v-model="countryCodes"
                multiple
                filterable
                allow-create
                default-first-option
                clearable
                placeholder="选择或输入国家代码"
                @change="onSourceFilterChange"
              >
                <el-option
                  v-for="country in metadata.countries"
                  :key="country.code"
                  :label="countryOptionLabel(country)"
                  :value="country.code"
                />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.source_mode === 'tag'" label="节点标签" required>
              <el-select
                v-model="tags"
                multiple
                filterable
                allow-create
                default-first-option
                clearable
                placeholder="选择或输入标签"
                @change="onSourceFilterChange"
              >
                <el-option v-for="tag in metadata.tags" :key="tag" :label="tag" :value="tag" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.source_mode === 'subscription'" label="订阅来源" required>
              <el-select v-model="subscriptionIds" multiple filterable clearable placeholder="选择订阅" @change="onSourceFilterChange">
                <el-option
                  v-for="subscription in metadata.subscriptions"
                  :key="subscription.id"
                  :label="subscriptionOptionLabel(subscription)"
                  :value="subscription.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.source_mode !== 'manual'" label="协议类型">
              <el-select
                v-model="protocolTypes"
                multiple
                filterable
                allow-create
                default-first-option
                clearable
                placeholder="vmess / trojan / ss"
                @change="onSourceFilterChange"
              >
                <el-option v-for="protocol in metadata.protocol_types" :key="protocol" :label="protocol" :value="protocol" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item v-if="form.source_mode === 'manual'" label="指定节点来源" required>
            <div class="node-selection">
              <el-button :icon="Plus" @click="openNodePicker('source')">选择节点</el-button>
              <el-button v-if="nodeIds.length" @click="clearSelectedNodes">清空</el-button>
              <span class="node-count">已选 {{ nodeIds.length }} 个节点</span>
            </div>
            <div v-if="nodeIds.length" class="selected-node-list">
              <div v-for="nodeId in nodeIds" :key="nodeId" class="selected-node-item">
                <el-tag closable effect="plain" @close="removeSelectedNode(nodeId)">
                  {{ nodeLabelById(nodeId) }}
                </el-tag>
              </div>
            </div>
          </el-form-item>
        </el-tab-pane>

        <el-tab-pane label="调度策略" name="strategy">
          <div class="form-grid">
            <el-form-item required>
              <template #label>
                <span class="label-with-help">
                  调度策略
                  <el-popover placement="right" width="360" trigger="hover">
                    <template #reference>
                      <span class="help-icon" title="查看调度策略说明">?</span>
                    </template>
                    <div class="strategy-help">
                      <div v-for="item in strategyOptions" :key="item.value" class="strategy-help-item">
                        <strong>{{ item.label }}</strong>
                        <span>{{ item.description }}</span>
                      </div>
                    </div>
                  </el-popover>
                </span>
              </template>
              <el-select v-model="form.strategy">
                <el-option
                  v-for="item in strategyOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                >
                  <div class="strategy-option">
                    <span>{{ item.label }}</span>
                    <small>{{ item.description }}</small>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>
          </div>

          <div class="strategy-panel">
            <div class="strategy-panel-head">
              <strong>{{ currentStrategy.label }}</strong>
              <el-tag size="small" effect="plain">{{ currentStrategy.engine }}</el-tag>
            </div>
            <p>{{ currentStrategy.detail }}</p>
            <p class="strategy-source-note">
              当前策略会使用「基础配置」中的节点来源生成候选节点；下方选择只会在候选节点内进一步限制或排序。
            </p>
            <div class="strategy-chips">
              <el-tag v-for="item in currentStrategy.effects" :key="item" size="small" effect="plain">{{ item }}</el-tag>
            </div>
            <el-alert
              v-if="currentStrategy.notice"
              type="warning"
              :closable="false"
              show-icon
              style="margin-top: 10px"
              :title="currentStrategy.notice"
            />
          </div>

          <el-form-item v-if="strategyCanSelectNodes" :label="strategyNodeLabel">
            <div class="node-selection">
              <el-button :icon="Plus" @click="openNodePicker('strategy')">从候选节点选择</el-button>
              <el-button v-if="strategyNodeIds.length" @click="clearStrategyNodes">清空</el-button>
              <span class="node-count">
                {{ strategyNodeIds.length ? `已选 ${strategyNodeIds.length} 个策略节点` : '未选择时使用基础配置中的全部候选节点' }}
              </span>
            </div>
            <div v-if="strategyNodeIds.length" class="selected-node-list" :class="{ ordered: strategyUsesOrder }">
              <div v-for="(nodeId, index) in strategyNodeIds" :key="nodeId" class="selected-node-item">
                <span v-if="strategyUsesOrder" class="node-order">{{ index + 1 }}</span>
                <el-tag closable effect="plain" @close="removeStrategyNode(nodeId)">
                  {{ nodeLabelById(nodeId) }}
                </el-tag>
                <template v-if="strategyUsesOrder">
                  <el-button
                    :icon="ArrowUp"
                    circle
                    size="small"
                    title="上移"
                    :disabled="index === 0"
                    @click="moveStrategyNode(index, -1)"
                  />
                  <el-button
                    :icon="ArrowDown"
                    circle
                    size="small"
                    title="下移"
                    :disabled="index === strategyNodeIds.length - 1"
                    @click="moveStrategyNode(index, 1)"
                  />
                </template>
              </div>
            </div>
          </el-form-item>

          <div v-if="strategyUsesHealthCheck || form.strategy === 'url-test'" class="form-grid">
            <el-form-item label="健康检测 URL" required>
              <el-input v-model="form.health_check_url" />
            </el-form-item>
            <el-form-item v-if="strategyUsesHealthCheck" label="检测间隔（秒）" required>
              <el-input-number v-model="form.health_check_interval" :min="30" style="width: 100%" />
            </el-form-item>
            <el-form-item v-if="form.strategy === 'url-test'" label="延迟容差（ms）" required>
              <el-input-number v-model="form.tolerance" :min="0" style="width: 100%" />
            </el-form-item>
          </div>
        </el-tab-pane>

        <el-tab-pane label="安全性" name="security">
          <div class="form-grid">
            <el-form-item label="用户名">
              <el-input v-model="form.username" placeholder="可选" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="form.password" placeholder="可选" show-password />
            </el-form-item>
            <el-form-item label="访问 Token">
              <el-input v-model="form.access_token" placeholder="可选；客户端使用 token 作为用户名" show-password />
            </el-form-item>
          </div>
          <el-form-item label="IP 白名单">
            <el-input
              v-model="ipWhitelistText"
              type="textarea"
              :rows="4"
              placeholder="可选；每行或逗号分隔，例如 127.0.0.1、192.168.1.0/24"
            />
          </el-form-item>
        </el-tab-pane>

        <el-tab-pane label="代理配置" name="policy">
          <el-form-item label="使用全局流量策略">
            <el-switch v-model="form.use_global_traffic_policy" />
          </el-form-item>
          <template v-if="!form.use_global_traffic_policy">
            <div class="form-grid">
              <el-form-item label="流量保护">
                <el-switch v-model="form.traffic_guard_enabled" />
              </el-form-item>
              <el-form-item label="排除未知流量订阅">
                <el-switch v-model="form.exclude_unknown_traffic" />
              </el-form-item>
              <el-form-item label="最低剩余流量（MB）">
                <el-input-number v-model="form.min_remaining_mb" :min="0" style="width: 100%" />
              </el-form-item>
              <el-form-item label="低流量降权阈值（MB）">
                <el-input-number v-model="form.low_remaining_mb" :min="0" style="width: 100%" />
              </el-form-item>
              <el-form-item label="即将到期降权（天）">
                <el-input-number v-model="form.expire_soon_days" :min="0" style="width: 100%" />
              </el-form-item>
            </div>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="生效流量保护">{{ effectiveTrafficConfig.traffic_guard_enabled ? '开启' : '关闭' }}</el-descriptions-item>
            <el-descriptions-item label="排除未知">{{ effectiveTrafficConfig.exclude_unknown_traffic ? '是' : '否' }}</el-descriptions-item>
            <el-descriptions-item label="最低剩余">{{ effectiveTrafficConfig.min_remaining_mb }} MB</el-descriptions-item>
            <el-descriptions-item label="低流量阈值">{{ effectiveTrafficConfig.low_remaining_mb }} MB</el-descriptions-item>
            <el-descriptions-item label="即将到期">{{ effectiveTrafficConfig.expire_soon_days }} 天</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
      </el-tabs>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="nodePickerVisible" :title="nodePickerTitle" width="980px">
    <div class="node-picker-toolbar">
      <el-input v-model="nodeQ" placeholder="搜索节点/服务器/来源" clearable @change="loadNodeOptions" />
      <el-select v-model="nodeCountry" filterable clearable placeholder="国家/地区" @change="loadNodeOptions">
        <el-option
          v-for="country in metadata.countries"
          :key="country.code"
          :label="countryOptionLabel(country)"
          :value="country.code"
        />
      </el-select>
      <el-input v-model="nodeGroup" placeholder="分组" clearable @change="loadNodeOptions" />
      <el-button :icon="Refresh" :loading="nodePickerLoading" @click="loadNodeOptions">刷新</el-button>
    </div>
    <el-table :data="nodeOptions" stripe height="420" empty-text="暂无可选节点">
      <el-table-column width="54">
        <template #default="{ row }">
          <el-checkbox
            :model-value="nodeSelectionDraft.includes(row.id)"
            @change="handleNodeDraftChange(row.id, $event)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="name" label="节点" min-width="260" show-overflow-tooltip class-name="table-cell-left" />
      <el-table-column prop="source_subscription_name" label="来源" min-width="130" show-overflow-tooltip class-name="table-cell-left" />
      <el-table-column prop="type" label="协议" width="90" />
      <el-table-column prop="country_code" label="国家" width="90" />
      <el-table-column label="延迟" width="110">
        <template #default="{ row }">{{ formatDelay(row.latency) }}</template>
      </el-table-column>
      <el-table-column prop="server" label="服务器" min-width="180" show-overflow-tooltip class-name="table-cell-left" />
    </el-table>
    <div class="selected-node-list picker-selected">
      <el-tag
        v-for="nodeId in nodeSelectionDraft"
        :key="nodeId"
        closable
        effect="plain"
        @close="toggleNodeDraft(nodeId, false)"
      >
        {{ nodeLabelById(nodeId) }}
      </el-tag>
    </div>
    <template #footer>
      <el-button @click="nodePickerVisible = false">取消</el-button>
      <el-button type="primary" @click="confirmNodeSelection">确定选择 {{ nodeSelectionDraft.length }} 个</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="runtimeVisible" title="Mihomo Runtime 配置" width="760px">
    <textarea class="code-editor" readonly :value="runtimeContent" />
  </el-dialog>

  <el-dialog v-model="globalConfigVisible" title="智能代理全局配置" width="760px">
    <el-form label-position="top">
      <div class="strategy-panel">
        <div class="strategy-panel-head">
          <strong>部署端口范围</strong>
          <el-tag size="small" effect="plain">
            {{ globalConfig.smart_proxy_port_start }} - {{ globalConfig.smart_proxy_port_end }}
          </el-tag>
        </div>
        <p>
          新增智能代理未手动指定端口时，系统会在该范围内自动分配可用监听端口；编辑代理时，监听端口也会限制在这个范围内。
        </p>
        <p class="strategy-source-note">
          该范围用于避免智能代理端口与其他服务冲突。已创建代理会保留自己的端口，重新应用到 Mihomo 不会自动改动现有端口。
        </p>
        <div class="strategy-chips">
          <el-tag size="small" effect="plain">自动分配</el-tag>
          <el-tag size="small" effect="plain">端口唯一</el-tag>
          <el-tag size="small" effect="plain">编辑时受限</el-tag>
        </div>
      </div>
      <div class="form-grid">
        <el-form-item>
          <template #label>
            <span class="label-with-help">
              定时检查并按需应用到 Mihomo（分钟，0 表示关闭）
              <el-popover placement="top" width="360" trigger="hover">
                <template #reference>
                  <span class="help-icon" title="查看按需应用说明">?</span>
                </template>
                <div class="strategy-help">
                  <div class="strategy-help-item">
                    <strong>默认关闭</strong>
                    <span>建议日常编辑代理时保持 0，避免配置在未手动确认时被后台热重载。</span>
                  </div>
                  <div class="strategy-help-item">
                    <strong>开启后</strong>
                    <span>系统会按间隔检查 runtime 内容，仅在配置发生变化时热重载 Mihomo。</span>
                  </div>
                  <div class="strategy-help-item">
                    <strong>适用场景</strong>
                    <span>更适合长期运行环境，用来同步节点池、订阅流量策略或候选节点变化。</span>
                  </div>
                </div>
              </el-popover>
            </span>
          </template>
          <el-input-number v-model="globalConfig.smart_proxy_auto_apply_interval_minutes" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="监控频率（分钟）">
          <el-input-number v-model="globalConfig.smart_proxy_monitor_interval_minutes" :min="0" style="width: 100%" />
        </el-form-item>
      </div>
      <div class="form-grid">
        <el-form-item label="Nebula 写入路径">
          <el-input v-model="globalConfig.mihomo_runtime_config_path" />
        </el-form-item>
        <el-form-item label="Mihomo 读取路径">
          <el-input v-model="globalConfig.mihomo_core_config_path" />
        </el-form-item>
      </div>
      <el-divider />
      <div class="form-grid">
        <el-form-item label="流量保护">
          <el-switch v-model="globalConfig.traffic_guard_enabled" />
        </el-form-item>
        <el-form-item label="排除未知流量订阅">
          <el-switch v-model="globalConfig.exclude_unknown_traffic" />
        </el-form-item>
        <el-form-item label="最低剩余流量（MB）">
          <el-input-number v-model="globalConfig.min_remaining_mb" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="低流量降权阈值（MB）">
          <el-input-number v-model="globalConfig.low_remaining_mb" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="即将到期降权天数">
          <el-input-number v-model="globalConfig.expire_soon_days" :min="0" style="width: 100%" />
        </el-form-item>
      </div>
    </el-form>
    <template #footer>
      <el-button @click="globalConfigVisible = false">取消</el-button>
      <el-button type="primary" @click="saveGlobalConfig">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="switchLogsVisible" :title="`节点切换历史${selectedSwitchProxy ? ` - ${selectedSwitchProxy.name}` : ''}`" width="860px">
    <el-table :data="switchLogs" stripe max-height="420" empty-text="暂无节点切换记录">
      <el-table-column prop="created_at" label="时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="from_node" label="原节点" min-width="220" show-overflow-tooltip class-name="table-cell-left">
        <template #default="{ row }">{{ row.from_node || '-' }}</template>
      </el-table-column>
      <el-table-column prop="to_node" label="新节点" min-width="220" show-overflow-tooltip class-name="table-cell-left" />
      <el-table-column prop="reason" label="切换原因" min-width="180" show-overflow-tooltip class-name="table-cell-left" />
    </el-table>
  </el-dialog>

  <el-dialog v-model="healthVisible" :title="`代理诊断${selectedDiagnosisProxy ? ` - ${selectedDiagnosisProxy.name}` : ''}`" width="920px">
    <div class="diagnosis-guide">
      <div>
        <strong>选择诊断方式</strong>
        <p>运行状态读取当前 Mihomo 运行态；健康检测会对节点执行延迟和场景检测，耗时更久。</p>
      </div>
      <div class="diagnosis-actions">
        <el-button
          :icon="DataAnalysis"
          :loading="diagnosisMode === 'status'"
          :disabled="diagnosisLoading"
          @click="runDiagnosis('status')"
        >
          只看运行状态
        </el-button>
        <el-button
          :icon="Refresh"
          :loading="diagnosisMode === 'health'"
          :disabled="diagnosisLoading"
          @click="runDiagnosis('health')"
        >
          只做健康检测
        </el-button>
        <el-button
          type="primary"
          :icon="DataAnalysis"
          :loading="diagnosisMode === 'all'"
          :disabled="diagnosisLoading"
          @click="runDiagnosis('all')"
        >
          全部执行
        </el-button>
      </div>
    </div>
    <el-empty
      v-if="!selectedStatus && !selectedHealth && !diagnosisLoading"
      description="请选择上方诊断方式"
    />
    <template v-if="selectedStatus">
      <div class="toolbar diagnosis-section-title">
        <h3>运行状态</h3>
      </div>
      <el-descriptions :column="3" border style="margin-bottom: 14px">
        <el-descriptions-item label="代理">{{ selectedStatus.name }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusTag(selectedStatus.status)">{{ runtimeStatusText(selectedStatus.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="当前节点">{{ selectedStatus.current_node || '-' }}</el-descriptions-item>
        <el-descriptions-item label="延迟">{{ formatDelay(selectedStatus.delay) }}</el-descriptions-item>
        <el-descriptions-item label="候选节点">{{ selectedStatus.candidate_nodes }}</el-descriptions-item>
        <el-descriptions-item label="运行节点">{{ selectedStatus.runtime_nodes }}</el-descriptions-item>
        <el-descriptions-item label="在线节点">{{ selectedStatus.online_nodes }}</el-descriptions-item>
        <el-descriptions-item label="失败节点">{{ selectedStatus.failed_nodes }}</el-descriptions-item>
        <el-descriptions-item label="平均延迟">{{ formatDelay(selectedStatus.average_delay) }}</el-descriptions-item>
        <el-descriptions-item label="最优节点">{{ selectedStatus.best_node || '-' }}</el-descriptions-item>
        <el-descriptions-item label="活动连接">{{ selectedStatus.active_connections }}</el-descriptions-item>
        <el-descriptions-item label="在线来源">{{ selectedStatus.online_users }}</el-descriptions-item>
        <el-descriptions-item label="上传速率">{{ formatRate(selectedStatus.upload_speed) }}</el-descriptions-item>
        <el-descriptions-item label="下载速率">{{ formatRate(selectedStatus.download_speed) }}</el-descriptions-item>
        <el-descriptions-item label="切换次数">{{ selectedStatus.switch_count }}</el-descriptions-item>
        <el-descriptions-item label="未授权连接">{{ selectedStatus.unauthorized_connections }}</el-descriptions-item>
        <el-descriptions-item label="流量保护">{{ selectedStatus.traffic_guard_enabled ? '开启' : '关闭' }}</el-descriptions-item>
        <el-descriptions-item label="流量排除">{{ selectedStatus.traffic_excluded_nodes }}</el-descriptions-item>
        <el-descriptions-item label="低流量风险">{{ selectedStatus.traffic_risk_nodes }}</el-descriptions-item>
        <el-descriptions-item label="流量快照">{{ selectedStatus.traffic_snapshot_at ? formatDateTime(selectedStatus.traffic_snapshot_at) : '-' }}</el-descriptions-item>
        <el-descriptions-item label="策略组">{{ selectedStatus.group_name }}</el-descriptions-item>
        <el-descriptions-item label="错误">{{ statusMessageText(selectedStatus.error) }}</el-descriptions-item>
        <el-descriptions-item label="来源 IP" :span="3">{{ selectedStatus.source_ips.length ? selectedStatus.source_ips.join(', ') : '-' }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="selectedStatus.traffic_reasons?.length"
        type="warning"
        :closable="false"
        style="margin-bottom: 14px"
        :title="trafficReasonsText(selectedStatus.traffic_reasons)"
      />
    </template>
    <template v-if="selectedHealth">
      <div class="toolbar diagnosis-section-title">
        <h3>健康检测</h3>
      </div>
      <el-descriptions :column="3" border style="margin-bottom: 14px">
        <el-descriptions-item label="代理">{{ selectedHealth.name }}</el-descriptions-item>
        <el-descriptions-item label="状态">
            <el-tag :type="statusTag(selectedHealth.status)">{{ readableStatusText(selectedHealth.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="检测时间">{{ formatDateTime(selectedHealth.checked_at) }}</el-descriptions-item>
        <el-descriptions-item label="在线">{{ selectedHealth.online_nodes }}/{{ selectedHealth.total_nodes }}</el-descriptions-item>
        <el-descriptions-item label="平均延迟">{{ formatDelay(selectedHealth.average_delay) }}</el-descriptions-item>
        <el-descriptions-item label="最优节点">{{ selectedHealth.best_node || '-' }}</el-descriptions-item>
        <el-descriptions-item label="当前节点" :span="2">{{ selectedHealth.current_node || '-' }}</el-descriptions-item>
        <el-descriptions-item label="错误">{{ statusMessageText(selectedHealth.error) }}</el-descriptions-item>
      </el-descriptions>
      <el-table :data="selectedHealth.checks" stripe max-height="220" style="margin-bottom: 14px">
        <el-table-column label="检测项" width="120">
          <template #default="{ row }">{{ checkTypeText(row.check_type) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)">{{ readableStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="延迟" width="100">
          <template #default="{ row }">{{ formatDelay(row.delay) }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="220" show-overflow-tooltip class-name="table-cell-left">
          <template #default="{ row }">{{ statusMessageText(row.message) }}</template>
        </el-table-column>
      </el-table>
      <el-table :data="selectedHealth.nodes" stripe max-height="320">
        <el-table-column prop="name" label="节点" min-width="260" show-overflow-tooltip class-name="table-cell-left" />
        <el-table-column prop="source" label="来源" width="110" />
        <el-table-column prop="type" label="协议" width="90" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)">{{ readableStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="延迟" width="100">
          <template #default="{ row }">{{ formatDelay(row.delay) }}</template>
        </el-table-column>
        <el-table-column label="当前" width="80">
          <template #default="{ row }">{{ row.current ? '是' : '-' }}</template>
        </el-table-column>
      </el-table>
      <div class="diagnosis-log-entry">
        <el-button :icon="DataAnalysis" @click="healthLogsVisible = true">
          查看最近检测日志（{{ healthLogs.length }}）
        </el-button>
      </div>
    </template>
    <template #footer>
      <el-button @click="healthVisible = false">关闭</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="healthLogsVisible" title="最近检测日志" width="860px">
    <el-table :data="healthLogs" stripe max-height="460" empty-text="暂无检测日志">
      <el-table-column prop="created_at" label="时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="检测项" width="110">
        <template #default="{ row }">{{ checkTypeText(row.check_type) }}</template>
      </el-table-column>
      <el-table-column prop="node_name" label="节点" min-width="220" show-overflow-tooltip class-name="table-cell-left" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)">{{ readableStatusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="延迟" width="90">
        <template #default="{ row }">{{ formatDelay(row.latency) }}</template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="healthLogsVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ArrowDown, ArrowUp, DataAnalysis, Delete, DocumentCopy, Edit, Lock, Plus, Refresh, Setting, Switch, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import http from '@/api/http'
import { useStatusSocket } from '@/composables/useStatusSocket'
import { copyText } from '@/utils/clipboard'
import { formatDateTime } from '@/utils/datetime'

interface SmartProxy {
  id: number
  name: string
  description?: string | null
  proxy_type: string
  listen_host: string
  port: number
  strategy: string
  stability_priority: boolean
  scenario: string
  source_mode: string
  subscription_ids: number[]
  country_codes: string[]
  tags: string[]
  node_ids: number[]
  strategy_node_ids: number[]
  protocol_types: string[]
  health_check_url: string
  health_check_interval: number
  tolerance: number
  username?: string | null
  password?: string | null
  access_token?: string | null
  ip_whitelist: string[]
  use_global_traffic_policy?: boolean
  traffic_guard_enabled?: boolean | null
  min_remaining_mb?: number | null
  low_remaining_mb?: number | null
  expire_soon_days?: number | null
  exclude_unknown_traffic?: boolean | null
  enabled: boolean
  status: string
  last_error?: string | null
  current_node?: string | null
  switch_count: number
  last_applied_at?: string | null
  config_updated_at?: string | null
  endpoint: string
  candidate_nodes: number
  runtime_apply_error?: string | null
  apply_status?: string | null
  apply_status_reason?: string | null
}

interface SmartProxyPreset {
  key: string
  name: string
  description: string
  proxy_type: string
  strategy: string
  stability_priority: boolean
  scenario: string
  source_mode: string
  country_codes: string[]
  tags: string[]
  protocol_types: string[]
  health_check_url: string
  health_check_interval: number
  tolerance: number
}

interface SmartProxyCountryOption {
  code: string
  name?: string | null
  nodes: number
}

interface SmartProxySubscriptionOption {
  id: number
  name: string
  group_name: string
  enabled: boolean
  nodes: number
}

interface SmartProxyMetadata {
  countries: SmartProxyCountryOption[]
  subscriptions: SmartProxySubscriptionOption[]
  tags: string[]
  protocol_types: string[]
  presets: SmartProxyPreset[]
}

interface NodeItem {
  id: number
  name: string
  type?: string | null
  server?: string | null
  port?: number | string | null
  country?: string | null
  country_code?: string | null
  tags: string[]
  latency?: number | null
  source_subscription_id?: number | null
  source_subscription_name?: string | null
  source_group?: string | null
  enabled: boolean
  last_seen_at?: string | null
}

type NodePickerMode = 'source' | 'strategy'

interface MihomoCoreStatus {
  api_url: string
  available: boolean
  version?: string | null
  active_connections: number
  download_total: number
  upload_total: number
  download_speed: number
  upload_speed: number
  memory?: number | null
  error?: string | null
}

interface SmartProxyStatus {
  proxy_id: number
  name: string
  endpoint: string
  group_name: string
  enabled: boolean
  core_available: boolean
  status: string
  current_node?: string | null
  candidate_nodes: number
  runtime_nodes: number
  online_nodes: number
  failed_nodes: number
  average_delay?: number | null
  best_node?: string | null
  active_connections: number
  online_users: number
  source_ips: string[]
  upload_total: number
  download_total: number
  upload_speed: number
  download_speed: number
  unauthorized_connections: number
  switch_count: number
  traffic_guard_enabled: boolean
  traffic_excluded_nodes: number
  traffic_risk_nodes: number
  traffic_unknown_nodes: number
  traffic_snapshot_at?: string | null
  traffic_reasons: string[]
  delay?: number | null
  error?: string | null
}

interface SmartProxyNodeHealth {
  node_id?: number | null
  name: string
  source?: string | null
  type?: string | null
  status: string
  delay?: number | null
  current: boolean
  error?: string | null
}

interface SmartProxyHealthCheck {
  check_type: string
  status: string
  delay?: number | null
  message?: string | null
}

interface SmartProxyHealthResult {
  proxy_id: number
  name: string
  group_name: string
  checked_at: string
  status: string
  total_nodes: number
  online_nodes: number
  failed_nodes: number
  average_delay?: number | null
  best_node?: string | null
  current_node?: string | null
  nodes: SmartProxyNodeHealth[]
  checks: SmartProxyHealthCheck[]
  error?: string | null
}

interface SmartProxyHealthLog {
  id: number
  smart_proxy_id: number
  node_id?: number | null
  node_name?: string | null
  check_type: string
  status: string
  latency?: number | null
  message?: string | null
  created_at: string
}

interface SmartProxySwitchLog {
  id: number
  smart_proxy_id: number
  from_node?: string | null
  to_node: string
  reason?: string | null
  created_at: string
}

interface SmartProxyGlobalConfig {
  smart_proxy_port_start: number
  smart_proxy_port_end: number
  smart_proxy_auto_apply_interval_minutes: number
  smart_proxy_monitor_interval_minutes: number
  mihomo_runtime_config_path: string
  mihomo_core_config_path: string
  traffic_guard_enabled: boolean
  min_remaining_mb: number
  low_remaining_mb: number
  expire_soon_days: number
  exclude_unknown_traffic: boolean
  runtime_apply_error?: string | null
}

interface SmartProxyConfig {
  proxy_id: number
  use_global_traffic_policy: boolean
  traffic_guard_enabled?: boolean | null
  min_remaining_mb?: number | null
  low_remaining_mb?: number | null
  expire_soon_days?: number | null
  exclude_unknown_traffic?: boolean | null
  effective_traffic_guard_enabled: boolean
  effective_min_remaining_mb: number
  effective_low_remaining_mb: number
  effective_expire_soon_days: number
  effective_exclude_unknown_traffic: boolean
  runtime_apply_error?: string | null
}

const items = ref<SmartProxy[]>([])
const coreStatus = reactive<MihomoCoreStatus>({
  api_url: '',
  available: false,
  version: null,
  active_connections: 0,
  download_total: 0,
  upload_total: 0,
  download_speed: 0,
  upload_speed: 0,
  memory: null,
  error: null,
})
const loading = ref(false)
const reloading = ref(false)
const enforcingAccess = ref(false)
const dialogVisible = ref(false)
const runtimeVisible = ref(false)
const healthVisible = ref(false)
const healthLogsVisible = ref(false)
const globalConfigVisible = ref(false)
const runtimeContent = ref('')
const selectedStatus = ref<SmartProxyStatus | null>(null)
const selectedHealth = ref<SmartProxyHealthResult | null>(null)
const healthLogs = ref<SmartProxyHealthLog[]>([])
const switchLogsVisible = ref(false)
const switchLogs = ref<SmartProxySwitchLog[]>([])
const selectedSwitchProxy = ref<SmartProxy | null>(null)
const selectedDiagnosisProxy = ref<SmartProxy | null>(null)
const checkingId = ref<number | null>(null)
const diagnosisMode = ref<'status' | 'health' | 'all' | null>(null)
const editingId = ref<number | null>(null)
const activeDialogTab = ref('basic')
const creationMode = ref<'quick' | 'advanced' | 'manual'>('quick')
const selectedPresetKey = ref('')
const countryCodes = ref<string[]>([])
const tags = ref<string[]>([])
const subscriptionIds = ref<number[]>([])
const nodeIds = ref<number[]>([])
const strategyNodeIds = ref<number[]>([])
const protocolTypes = ref<string[]>([])
const metadataLoaded = ref(false)
const metadata = reactive<SmartProxyMetadata>({
  countries: [],
  subscriptions: [],
  tags: [],
  protocol_types: [],
  presets: [],
})
const nodePickerVisible = ref(false)
const nodePickerLoading = ref(false)
const nodeOptions = ref<NodeItem[]>([])
const nodeSelectionDraft = ref<number[]>([])
const nodePickerMode = ref<NodePickerMode>('source')
const nodeCache = ref<Record<number, NodeItem>>({})
const nodeQ = ref('')
const nodeCountry = ref('')
const nodeGroup = ref('')
const ipWhitelistText = ref('')
const form = reactive({
  name: '',
  description: '',
  proxy_type: 'mixed',
  listen_host: '127.0.0.1',
  port: null as number | null,
  strategy: 'fallback',
  stability_priority: false,
  scenario: 'general',
  source_mode: 'all',
  health_check_url: 'http://www.gstatic.com/generate_204',
  health_check_interval: 300,
  tolerance: 50,
  username: '',
  password: '',
  access_token: '',
  use_global_traffic_policy: true,
  traffic_guard_enabled: true,
  min_remaining_mb: 0,
  low_remaining_mb: 2048,
  expire_soon_days: 3,
  exclude_unknown_traffic: false,
  enabled: true,
})
const globalConfig = reactive<SmartProxyGlobalConfig>({
  smart_proxy_port_start: 37890,
  smart_proxy_port_end: 37900,
  smart_proxy_auto_apply_interval_minutes: 0,
  smart_proxy_monitor_interval_minutes: 1,
  mihomo_runtime_config_path: '',
  mihomo_core_config_path: '',
  traffic_guard_enabled: true,
  min_remaining_mb: 0,
  low_remaining_mb: 2048,
  expire_soon_days: 3,
  exclude_unknown_traffic: false,
})
const effectiveTrafficConfig = computed(() => ({
  traffic_guard_enabled: form.use_global_traffic_policy ? globalConfig.traffic_guard_enabled : Boolean(form.traffic_guard_enabled),
  min_remaining_mb: form.use_global_traffic_policy ? globalConfig.min_remaining_mb : Number(form.min_remaining_mb || 0),
  low_remaining_mb: form.use_global_traffic_policy ? globalConfig.low_remaining_mb : Number(form.low_remaining_mb || 0),
  expire_soon_days: form.use_global_traffic_policy ? globalConfig.expire_soon_days : Number(form.expire_soon_days || 0),
  exclude_unknown_traffic: form.use_global_traffic_policy ? globalConfig.exclude_unknown_traffic : Boolean(form.exclude_unknown_traffic),
}))
const strategyOptions = [
  {
    value: 'stable',
    label: '稳定优先',
    description: '固定当前可用节点，只有当前节点不可用时才切换，切换后新节点成为主节点。',
    engine: 'Mihomo fallback / sticky',
    detail: '适合游戏、账号登录和风控敏感应用。当前节点只要仍在候选池内、流量策略允许且 Mihomo 判断可用，就会保持为主节点；切换后不会因原节点恢复而自动切回。',
    effects: ['固定出口', '故障切换', '切换后粘滞'],
    notice: '适合要求代理 IP 稳定的场景；如果追求低延迟，请使用自动测速。',
  },
  {
    value: 'fallback',
    label: '故障转移',
    description: '按节点顺序使用第一个可用节点，当前节点不可用时自动切到下一个。',
    engine: 'Mihomo fallback',
    detail: '适合按固定主备顺序管理线路。候选节点来自基础配置的节点来源，可在策略节点中进一步选择并调整主备顺序。',
    effects: ['主备顺序', '健康检测', '故障切换'],
    notice: '如果应用对出口 IP 敏感，建议改用“稳定优先”。',
  },
  {
    value: 'url-test',
    label: '自动测速',
    description: '定期测试候选节点延迟，自动选择延迟最低的节点。',
    engine: 'Mihomo url-test',
    detail: '适合低延迟优先的线路。候选节点来自节点来源，Mihomo 会按检测 URL 和间隔测速，并根据延迟容差选择更快节点。',
    effects: ['自动测速', '最低延迟', '延迟容差'],
    notice: '延迟容差越小越容易切换，越大越稳定。',
  },
  {
    value: 'load-balance',
    label: '负载均衡',
    description: '按一致性哈希把不同连接分散到多个节点，适合多设备或批量请求。',
    engine: 'Mihomo load-balance',
    detail: '适合多设备共享或批量请求。候选节点来自节点来源，相同目标会尽量落到固定节点，不同连接会分散到多个可用节点。',
    effects: ['一致性哈希', '多节点分流', '健康检测'],
    notice: '不适合需要固定出口 IP 的登录态服务。',
  },
  {
    value: 'round-robin',
    label: '轮询',
    description: '按顺序轮流使用候选节点，尽量平均分配连接。',
    engine: 'Mihomo load-balance / round-robin',
    detail: '适合想平均使用多个节点的场景。候选节点来自基础配置的节点来源，新连接按策略节点顺序轮流分配。',
    effects: ['顺序轮换', '平均分配', '使用节点来源'],
    notice: '如果业务依赖固定出口 IP，请谨慎使用；策略节点建议至少选择 2 个节点。',
  },
  {
    value: 'select',
    label: '手动选择',
    description: '在 Mihomo 策略组中手动指定当前节点，不自动切换。',
    engine: 'Mihomo select',
    detail: '适合需要人工指定出口的场景。Nebula 根据基础配置的节点来源生成候选列表，可在下方限制可选节点范围。',
    effects: ['人工选择', '不自动切换', '候选列表'],
    notice: '该策略不会按检测间隔自动切换节点；如果希望当前节点故障时自动切换，并且切换后保持新节点，请使用“稳定优先”。',
  },
  {
    value: 'relay',
    label: '链式代理',
    description: '按顺序串联多个节点形成代理链，通常只适合高级场景。',
    engine: 'Mihomo relay',
    detail: '适合高级链路编排。流量会按策略节点顺序依次经过多个候选节点，列表第 1 个为入口链路，最后一个为出口链路。',
    effects: ['候选内选择', '顺序敏感', '链路串联'],
    notice: '请在下方链路节点中按顺序选择至少 2 个节点。',
  },
]
const currentStrategy = computed(() => strategyOptions.find((item) => item.value === form.strategy) || strategyOptions[0])
const strategyUsesHealthCheck = computed(() => ['stable', 'fallback', 'url-test', 'load-balance', 'round-robin'].includes(form.strategy))
const strategyCanSelectNodes = computed(() => ['stable', 'fallback', 'url-test', 'load-balance', 'round-robin', 'select', 'relay'].includes(form.strategy))
const strategyUsesOrder = computed(() => ['stable', 'fallback', 'round-robin', 'select', 'relay'].includes(form.strategy))
const diagnosisLoading = computed(() => diagnosisMode.value !== null)
const strategyNodeLabel = computed(() => {
  if (form.strategy === 'relay') return '链路节点'
  if (form.strategy === 'select') return '可选节点'
  if (form.strategy === 'stable') return '稳定节点顺序'
  if (form.strategy === 'fallback') return '主备节点顺序'
  if (form.strategy === 'round-robin') return '轮询节点顺序'
  return '策略节点范围'
})
const nodePickerTitle = computed(() => (nodePickerMode.value === 'strategy' ? `选择${strategyNodeLabel.value}` : '选择节点来源'))
const runtimeStatusOptions = [
  {
    value: 'running',
    label: '运行中',
    description: 'Mihomo 中已找到对应策略组和监听器，代理正在按当前策略转发连接。',
  },
  {
    value: 'configured',
    label: '已配置',
    description: '配置文件已生成，但页面尚未从 Mihomo 运行态确认到实时状态；稍后会自动刷新。',
  },
  {
    value: 'degraded',
    label: '异常',
    description: '代理已启用但运行不完整，常见原因是策略组缺失、候选节点为空或 Mihomo API 返回异常。',
  },
  {
    value: 'core_unavailable',
    label: '核心不可用',
    description: '当前无法连接 Mihomo API，代理运行状态无法确认。',
  },
  {
    value: 'stopped',
    label: '已停止',
    description: '代理未启用，不会写入或暴露对应的 Mihomo 监听服务。',
  },
]

function resetForm() {
  Object.assign(form, {
    name: '',
    description: '',
    proxy_type: 'mixed',
    listen_host: '127.0.0.1',
    port: null,
    strategy: 'fallback',
    stability_priority: false,
    scenario: 'general',
    source_mode: 'all',
    health_check_url: 'http://www.gstatic.com/generate_204',
    health_check_interval: 300,
    tolerance: 50,
    username: '',
    password: '',
    access_token: '',
    use_global_traffic_policy: true,
    traffic_guard_enabled: globalConfig.traffic_guard_enabled,
    min_remaining_mb: globalConfig.min_remaining_mb,
    low_remaining_mb: globalConfig.low_remaining_mb,
    expire_soon_days: globalConfig.expire_soon_days,
    exclude_unknown_traffic: globalConfig.exclude_unknown_traffic,
    enabled: true,
  })
  activeDialogTab.value = 'basic'
  creationMode.value = 'quick'
  selectedPresetKey.value = ''
  countryCodes.value = []
  tags.value = []
  subscriptionIds.value = []
  nodeIds.value = []
  strategyNodeIds.value = []
  protocolTypes.value = []
  nodeSelectionDraft.value = []
  nodePickerMode.value = 'source'
  ipWhitelistText.value = ''
  editingId.value = null
}

function typeLabel(value: string) {
  if (value === 'socks') return 'SOCKS5'
  if (value === 'mixed') return '混合代理'
  return 'HTTP'
}

function endpointWithScheme(endpoint: string, scheme: 'http' | 'socks5') {
  return endpoint.replace(/^[a-z][a-z0-9+.-]*:\/\//i, `${scheme}://`)
}

function endpointOptions(row: SmartProxy) {
  if (row.proxy_type === 'mixed') {
    return [
      { label: 'HTTP(S)', scheme: 'http', url: endpointWithScheme(row.endpoint, 'http') },
      { label: 'SOCKS5', scheme: 'socks5', url: endpointWithScheme(row.endpoint, 'socks5') },
    ]
  }
  if (row.proxy_type === 'socks') {
    return [{ label: 'SOCKS5', scheme: 'socks5', url: endpointWithScheme(row.endpoint, 'socks5') }]
  }
  return [{ label: 'HTTP(S)', scheme: 'http', url: endpointWithScheme(row.endpoint, 'http') }]
}

function strategyLabel(value: string, stabilityPriority = false) {
  if (stabilityPriority && ['select', 'fallback'].includes(value)) return '稳定优先'
  return strategyOptions.find((item) => item.value === value)?.label || value
}

function scenarioLabel(value: string) {
  const labels: Record<string, string> = {
    general: '通用',
    ai: 'AI',
    streaming: '流媒体',
    latency: '低延迟',
  }
  return labels[value] || value
}

function coreStatusText(available: boolean) {
  return available ? '可用' : '不可用'
}

function readableStatusText(value?: string | null) {
  const labels: Record<string, string> = {
    ok: '正常',
    online: '可用',
    healthy: '健康',
    running: '运行中',
    configured: '已配置',
    stopped: '已停止',
    degraded: '异常',
    core_unavailable: '核心不可用',
    failed: '不可用',
    unknown: '未知',
  }
  if (!value) return '未知'
  return labels[value] || runtimeStatusText(value)
}

function checkTypeText(value?: string | null) {
  const labels: Record<string, string> = {
    delay: '延迟检测',
    chatgpt: 'ChatGPT',
    netflix: 'Netflix',
  }
  if (!value) return '-'
  return labels[value] || value
}

function statusMessageText(value?: string | null) {
  if (!value) return '-'
  const labels: Record<string, string> = {
    'Delay check timed out': '延迟检测超时',
    'Scenario check timed out': '场景检测超时',
    'All candidate nodes timed out': '所有候选节点检测超时',
    'Smart proxy is stopped': '代理已停止',
    'Mihomo runtime group is missing; reload runtime config': 'Mihomo 运行策略组缺失，请重新应用配置',
    'Mihomo returned an unexpected delay payload': 'Mihomo 返回了无法识别的延迟数据',
    'No candidate nodes matched this smart proxy': '没有匹配到候选节点',
    'No traffic snapshot found; traffic scheduling skipped': '暂无流量快照，已跳过流量调度',
  }
  let text = labels[value] || value
  const replacements: Array<[string, string]> = [
    ['No usable nodes after traffic scheduling', '流量调度后没有可用节点'],
    ['subscription expired', '订阅已到期'],
    ['subscription traffic exhausted', '订阅流量已用尽'],
    ['subscription traffic is low', '订阅剩余流量较低'],
    ['subscription expires soon', '订阅即将到期'],
    ['Cannot connect to Mihomo API at', '无法连接 Mihomo API：'],
    ['Mihomo reload failed', 'Mihomo 热重载失败'],
  ]
  replacements.forEach(([source, target]) => {
    text = text.split(source).join(target)
  })
  return text
}

function trafficReasonsText(items?: string[] | null) {
  const values = (items || []).map((item) => statusMessageText(item)).filter((item) => item !== '-')
  return values.length ? values.join('；') : '-'
}

function runtimeStatusText(value?: string | null) {
  return runtimeStatusOptions.find((item) => item.value === value)?.label || value || '未知'
}

function runtimeStatusLabel(row: SmartProxy) {
  return runtimeStatusText(row.enabled ? row.status : 'stopped')
}

function runtimeStatusTag(row: SmartProxy) {
  return statusTag(row.enabled ? row.status : 'stopped')
}

function parseDateTime(value?: string | null) {
  if (!value) return null
  const normalized = value
    .replace(' ', 'T')
    .replace(/(\.\d{3})\d+/, '$1')
  const timestamp = Date.parse(normalized)
  return Number.isNaN(timestamp) ? null : timestamp
}

function resolvedApplyStatus(row: SmartProxy) {
  if (!row.enabled) return 'disabled'
  const appliedAt = parseDateTime(row.last_applied_at)
  const configUpdatedAt = parseDateTime(row.config_updated_at)
  if (appliedAt !== null) {
    if (configUpdatedAt !== null && appliedAt + 2000 < configUpdatedAt) return 'pending'
    if (row.status === 'degraded' && row.last_error) return 'failed'
    return 'applied'
  }
  return row.apply_status || 'pending'
}

function applyStatusLabel(row: SmartProxy) {
  const labels: Record<string, string> = {
    applied: '已应用',
    pending: '待应用',
    failed: '应用失败',
    disabled: '未启用',
  }
  return labels[resolvedApplyStatus(row)] || '未知'
}

function applyStatusType(row: SmartProxy) {
  const types: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    applied: 'success',
    pending: 'warning',
    failed: 'danger',
    disabled: 'info',
  }
  return types[resolvedApplyStatus(row)] || 'info'
}

function applyStatusReason(row: SmartProxy) {
  if (row.apply_status_reason) return statusMessageText(row.apply_status_reason)
  if (row.last_error) return statusMessageText(row.last_error)
  const reasons: Record<string, string> = {
    applied: '当前配置已成功应用到 Mihomo。',
    pending: '代理配置尚未应用到 Mihomo，请点击顶部“重新应用到 Mihomo”。',
    failed: '代理已应用，但运行状态异常，请查看运行状态或健康检测。',
    disabled: '代理未启用，不会出现在 Mihomo 运行配置中。',
  }
  return reasons[resolvedApplyStatus(row)] || '状态未知，请刷新后查看。'
}

function countryOptionLabel(country: SmartProxyCountryOption) {
  const name = country.name ? `${country.name} / ` : ''
  return `${name}${country.code}（${country.nodes}）`
}

function subscriptionOptionLabel(subscription: SmartProxySubscriptionOption) {
  const status = subscription.enabled ? '' : ' / 已停用'
  return `${subscription.name} / ${subscription.group_name}（${subscription.nodes}）${status}`
}

function trimApplyError(error: string) {
  return error.length > 180 ? `${error.slice(0, 180)}...` : error
}

function notifyRuntimeApply(error: string | null | undefined, successMessage: string) {
  if (error) {
    ElMessage.warning(`配置已保存，但 Mihomo 热重载失败：${trimApplyError(error)}`)
    return
  }
  ElMessage.success(successMessage)
}

async function confirmReloadRuntime() {
  try {
    await ElMessageBox.confirm(
      '重新应用会生成全部智能代理配置并热重载 Mihomo，可能会让其它代理的现有连接短暂中断或重建。是否继续？',
      '重新应用到 Mihomo',
      {
        type: 'warning',
        confirmButtonText: '重新应用',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }
  await reloadRuntime(true)
}

async function currentAutoApplyHint() {
  try {
    const data = await loadGlobalConfig()
    const minutes = Number(data.smart_proxy_auto_apply_interval_minutes || 0)
    if (minutes > 0) {
      return `当前已开启定时检查并按需应用到 Mihomo（${minutes} 分钟）。选择“仅保存”后不会立即热重载，但配置变化仍可能在下一次定时检查中生效。`
    }
  } catch {
    // Ignore config read failures; the save flow can still continue.
  }
  return '选择“仅保存”后，需要手动点击顶部“重新应用到 Mihomo”才会热重载。'
}

async function chooseApplyBeforeSave() {
  const hint = await currentAutoApplyHint()
  try {
    await ElMessageBox.confirm(
      `保存后是否立即应用到 Mihomo？立即应用会热重载 Mihomo，可能会让其它代理的现有连接短暂中断或重建。\n\n${hint}`,
      '保存配置',
      {
        type: 'warning',
        confirmButtonText: '保存并立即应用',
        cancelButtonText: '仅保存',
      },
    )
    return true
  } catch (action) {
    if (action === 'cancel') return false
    return null
  }
}

async function applyAfterSaved(applyNow: boolean) {
  if (!applyNow) {
    ElMessage.success('已保存，待应用到 Mihomo')
    await load()
    return
  }
  await reloadRuntime(true)
}

function splitListText(value: string) {
  return value
    .split(/[\n,，]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function clearManualNodes() {
  nodeIds.value = []
  nodeSelectionDraft.value = []
  if (form.source_mode === 'manual') strategyNodeIds.value = []
}

function clearStrategyNodes() {
  strategyNodeIds.value = []
  if (nodePickerMode.value === 'strategy') nodeSelectionDraft.value = []
}

function pruneStrategyNodesToManualSource() {
  if (form.source_mode !== 'manual' || !strategyNodeIds.value.length) return
  const sourceIds = new Set(nodeIds.value)
  strategyNodeIds.value = strategyNodeIds.value.filter((item) => sourceIds.has(item))
}

function clearSourceFiltersForMode(mode: string) {
  if (mode !== 'country') countryCodes.value = []
  if (mode !== 'tag') tags.value = []
  if (mode !== 'subscription') subscriptionIds.value = []
}

function onSourceFilterChange() {
  if (!strategyNodeIds.value.length) return
  strategyNodeIds.value = []
  ElMessage.info('节点来源筛选已变更，策略节点选择已清空')
}

function onSourceModeChange(value: string | number | boolean | undefined) {
  const mode = String(value || 'all')
  if (strategyNodeIds.value.length) {
    strategyNodeIds.value = []
    ElMessage.info('节点来源已变更，策略节点选择已清空')
  }
  if (mode === 'manual') {
    countryCodes.value = []
    tags.value = []
    subscriptionIds.value = []
    protocolTypes.value = []
  } else {
    if (nodeIds.value.length) {
      ElMessage.info('已切换为筛选模式，手动选择的节点已清空')
      clearManualNodes()
    }
    clearSourceFiltersForMode(mode)
  }
}

function validateStrategyBeforeSave() {
  if (form.source_mode === 'subscription' && subscriptionIds.value.length === 0) {
    ElMessage.warning('指定订阅模式请至少选择一个订阅来源')
    return false
  }
  if (form.source_mode === 'country' && countryCodes.value.length === 0) {
    ElMessage.warning('指定国家模式请至少选择一个国家/地区')
    return false
  }
  if (form.source_mode === 'tag' && tags.value.length === 0) {
    ElMessage.warning('指定标签模式请至少选择一个节点标签')
    return false
  }
  if (form.source_mode === 'manual' && strategyNodeIds.value.length) {
    const sourceIds = new Set(nodeIds.value)
    if (strategyNodeIds.value.some((item) => !sourceIds.has(item))) {
      ElMessage.warning('策略节点必须来自基础配置中的指定节点来源')
      return false
    }
  }
  const selectedStrategyCount = strategyNodeIds.value.length
  const knownCandidateCount = selectedStrategyCount || (form.source_mode === 'manual' ? nodeIds.value.length : null)
  if (form.strategy === 'relay' && knownCandidateCount !== null && knownCandidateCount < 2) {
    ElMessage.warning('链式代理请在候选节点中按顺序选择至少 2 个节点')
    return false
  }
  if (form.strategy === 'round-robin' && knownCandidateCount !== null && knownCandidateCount < 2) {
    ElMessage.warning('轮询策略请至少使用 2 个候选节点')
    return false
  }
  return true
}

async function load() {
  loading.value = true
  try {
    const [{ data }] = await Promise.all([http.get('/smart-proxies'), refreshCoreStatus()])
    items.value = data
    await refreshProxyStatuses()
  } finally {
    loading.value = false
  }
}

async function refreshCoreStatus() {
  const { data } = await http.get('/smart-proxies/core/status')
  Object.assign(coreStatus, data)
}

async function refreshProxyStatuses() {
  if (!items.value.length) return
  const results = await Promise.allSettled(
    items.value.map((item) => http.get(`/smart-proxies/${item.id}/status`, { params: { delay: false } })),
  )
  results.forEach((result) => {
    if (result.status !== 'fulfilled') return
    const data = result.value.data as SmartProxyStatus
    applySmartProxyStatus(data)
  })
}

async function refreshLiveState() {
  await Promise.allSettled([refreshCoreStatus(), refreshProxyStatuses()])
}

function applySmartProxyStatus(data: SmartProxyStatus) {
  const target = items.value.find((item) => item.id === data.proxy_id)
  if (!target) return
  target.status = data.status
  target.current_node = data.current_node
  target.switch_count = data.switch_count
  target.candidate_nodes = data.candidate_nodes
}

const { connect: connectStatusSocket, stop: stopStatusSocket } = useStatusSocket((message) => {
  const payload = message.smart_proxies as { core?: MihomoCoreStatus; proxies?: SmartProxyStatus[] } | undefined
  if (!payload) return
  if (payload.core) Object.assign(coreStatus, payload.core)
  if (Array.isArray(payload.proxies)) {
    payload.proxies.forEach(applySmartProxyStatus)
  }
}, { topics: ['smart_proxies'], intervalMs: 10000 })

async function loadMetadata(force = false) {
  if (metadataLoaded.value && !force) return
  const { data } = await http.get('/smart-proxies/metadata')
  Object.assign(metadata, data)
  metadataLoaded.value = true
}

async function loadGlobalConfig() {
  const { data } = await http.get('/smart-proxies/config/global')
  Object.assign(globalConfig, data)
  return data as SmartProxyGlobalConfig
}

function applyTrafficConfigToForm(data: SmartProxyConfig) {
  form.use_global_traffic_policy = data.use_global_traffic_policy
  if (!data.use_global_traffic_policy) {
    form.traffic_guard_enabled = data.traffic_guard_enabled ?? data.effective_traffic_guard_enabled
    form.min_remaining_mb = data.min_remaining_mb ?? data.effective_min_remaining_mb
    form.low_remaining_mb = data.low_remaining_mb ?? data.effective_low_remaining_mb
    form.expire_soon_days = data.expire_soon_days ?? data.effective_expire_soon_days
    form.exclude_unknown_traffic = data.exclude_unknown_traffic ?? data.effective_exclude_unknown_traffic
    return
  }
  form.traffic_guard_enabled = data.effective_traffic_guard_enabled
  form.min_remaining_mb = data.effective_min_remaining_mb
  form.low_remaining_mb = data.effective_low_remaining_mb
  form.expire_soon_days = data.effective_expire_soon_days
  form.exclude_unknown_traffic = data.effective_exclude_unknown_traffic
}

function applyPreset(preset: SmartProxyPreset) {
  const previousPreset = metadata.presets.find((item) => item.key === selectedPresetKey.value)
  const shouldReplaceName = !form.name || Boolean(previousPreset && form.name === previousPreset.name)
  selectedPresetKey.value = preset.key
  Object.assign(form, {
    name: shouldReplaceName ? preset.name : form.name,
    proxy_type: preset.proxy_type,
    strategy: preset.strategy,
    stability_priority: preset.strategy === 'stable',
    scenario: preset.scenario,
    source_mode: preset.source_mode,
    health_check_url: preset.health_check_url,
    health_check_interval: preset.health_check_interval,
    tolerance: preset.tolerance,
  })
  countryCodes.value = [...preset.country_codes]
  tags.value = [...preset.tags]
  protocolTypes.value = [...preset.protocol_types]
  subscriptionIds.value = []
  nodeIds.value = []
  strategyNodeIds.value = []
}

function onCreationModeChange(value: string | number | boolean | undefined) {
  if (value === 'manual') {
    const preset = metadata.presets.find((item) => item.key === selectedPresetKey.value)
    if (preset && form.name === preset.name) form.name = ''
    form.source_mode = 'manual'
    selectedPresetKey.value = ''
    countryCodes.value = []
    tags.value = []
    subscriptionIds.value = []
    protocolTypes.value = []
    strategyNodeIds.value = []
  } else if (value === 'advanced') {
    const preset = metadata.presets.find((item) => item.key === selectedPresetKey.value)
    if (preset && form.name === preset.name) form.name = ''
    selectedPresetKey.value = ''
    if (form.source_mode === 'manual') form.source_mode = 'all'
    countryCodes.value = []
    tags.value = []
    subscriptionIds.value = []
    clearManualNodes()
    strategyNodeIds.value = []
    protocolTypes.value = []
  } else if (value === 'quick') {
    const preset = metadata.presets[0]
    if (preset) applyPreset(preset)
  }
}

async function openCreate() {
  resetForm()
  await Promise.all([loadMetadata(), loadGlobalConfig()])
  Object.assign(form, {
    traffic_guard_enabled: globalConfig.traffic_guard_enabled,
    min_remaining_mb: globalConfig.min_remaining_mb,
    low_remaining_mb: globalConfig.low_remaining_mb,
    expire_soon_days: globalConfig.expire_soon_days,
    exclude_unknown_traffic: globalConfig.exclude_unknown_traffic,
  })
  const preset = metadata.presets[0]
  if (preset) applyPreset(preset)
  dialogVisible.value = true
}

async function openEdit(row: SmartProxy) {
  resetForm()
  await Promise.all([loadMetadata(), loadGlobalConfig()])
  editingId.value = row.id
  creationMode.value = row.source_mode === 'manual' ? 'manual' : 'advanced'
  Object.assign(form, {
    name: row.name,
    description: row.description || '',
    proxy_type: row.proxy_type,
    listen_host: row.listen_host,
    port: row.port,
    strategy: row.strategy,
    stability_priority: row.strategy === 'stable',
    scenario: row.scenario,
    source_mode: row.source_mode,
    health_check_url: row.health_check_url,
    health_check_interval: row.health_check_interval,
    tolerance: row.tolerance,
    username: row.username || '',
    password: row.password || '',
    access_token: row.access_token || '',
    enabled: row.enabled,
  })
  countryCodes.value = [...row.country_codes]
  tags.value = [...row.tags]
  subscriptionIds.value = [...row.subscription_ids]
  nodeIds.value = [...row.node_ids]
  strategyNodeIds.value = [...(row.strategy_node_ids || [])]
  pruneStrategyNodesToManualSource()
  await loadNodeLabelCache([...nodeIds.value, ...strategyNodeIds.value])
  protocolTypes.value = [...row.protocol_types]
  ipWhitelistText.value = (row.ip_whitelist || []).join('\n')
  const { data: config } = await http.get(`/smart-proxies/${row.id}/config`)
  applyTrafficConfigToForm(config)
  dialogVisible.value = true
}

function payload() {
  const mode = form.source_mode
  const { use_global_traffic_policy: useGlobalTrafficPolicy, ...formPayload } = form
  return {
    ...formPayload,
    description: form.description || null,
    username: form.username || null,
    password: form.password || null,
    access_token: form.access_token || null,
    stability_priority: form.strategy === 'stable',
    traffic_guard_enabled: useGlobalTrafficPolicy ? null : Boolean(form.traffic_guard_enabled),
    min_remaining_mb: useGlobalTrafficPolicy ? null : Number(form.min_remaining_mb || 0),
    low_remaining_mb: useGlobalTrafficPolicy ? null : Number(form.low_remaining_mb || 0),
    expire_soon_days: useGlobalTrafficPolicy ? null : Number(form.expire_soon_days || 0),
    exclude_unknown_traffic: useGlobalTrafficPolicy ? null : Boolean(form.exclude_unknown_traffic),
    country_codes: mode === 'country' ? countryCodes.value.map((item) => item.trim().toUpperCase()).filter(Boolean) : [],
    tags: mode === 'tag' ? tags.value.map((item) => item.trim()).filter(Boolean) : [],
    subscription_ids: mode === 'subscription' ? subscriptionIds.value : [],
    node_ids: mode === 'manual' ? nodeIds.value : [],
    strategy_node_ids: strategyNodeIds.value,
    protocol_types: mode === 'manual' ? [] : protocolTypes.value.map((item) => item.trim().toLowerCase()).filter(Boolean),
    ip_whitelist: splitListText(ipWhitelistText.value),
  }
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写代理名称')
    return
  }
  if (form.source_mode === 'manual' && nodeIds.value.length === 0) {
    ElMessage.warning('手动节点模式请至少选择一个节点')
    return
  }
  if (!validateStrategyBeforeSave()) return
  const applyNow = await chooseApplyBeforeSave()
  if (applyNow === null) return
  if (editingId.value) await http.put(`/smart-proxies/${editingId.value}`, payload())
  else await http.post('/smart-proxies', payload())
  dialogVisible.value = false
  await applyAfterSaved(applyNow)
}

async function loadNodeOptions() {
  nodePickerLoading.value = true
  try {
    const { data } = await http.get('/nodes', {
      params: {
        q: nodeQ.value || undefined,
        country: nodeCountry.value || undefined,
        group: nodeGroup.value || undefined,
        enabled: true,
      },
    })
    const items = data.items.filter((item: NodeItem) => Number.isInteger(item.id))
    items.forEach((item: NodeItem) => {
      nodeCache.value[item.id] = item
    })
    nodeOptions.value = nodePickerMode.value === 'strategy'
      ? items.filter((item: NodeItem) => sourceNodeMatches(item))
      : items
  } finally {
    nodePickerLoading.value = false
  }
}

async function loadNodeLabelCache(nodeIdsToLoad: number[]) {
  const missingIds = [...new Set(nodeIdsToLoad)].filter((nodeId) => Number.isInteger(nodeId) && !nodeCache.value[nodeId])
  if (!missingIds.length) return
  const { data } = await http.get('/nodes')
  const items = data.items.filter((item: NodeItem) => Number.isInteger(item.id))
  items.forEach((item: NodeItem) => {
    nodeCache.value[item.id] = item
  })
}

function normalizedProtocolTypes() {
  return protocolTypes.value.map((item) => item.trim().toLowerCase()).filter(Boolean)
}

function sourceNodeMatches(node: NodeItem) {
  if (!node.enabled) return false
  if (form.source_mode !== 'manual') {
    const protocols = normalizedProtocolTypes()
    if (protocols.length && !protocols.includes(String(node.type || '').toLowerCase())) return false
  }
  if (form.source_mode === 'manual') return nodeIds.value.includes(node.id)
  if (form.source_mode === 'subscription') {
    if (!subscriptionIds.value.length) return false
    return node.source_subscription_id !== null && node.source_subscription_id !== undefined && subscriptionIds.value.includes(Number(node.source_subscription_id))
  }
  if (form.source_mode === 'country') {
    if (!countryCodes.value.length) return false
    const selectedCountries = countryCodes.value.map((item) => item.trim().toUpperCase()).filter(Boolean)
    return selectedCountries.includes(String(node.country_code || '').toUpperCase())
  }
  if (form.source_mode === 'tag') {
    if (!tags.value.length) return false
    const selectedTags = new Set(tags.value.map((item) => item.trim()).filter(Boolean))
    return (node.tags || []).some((item) => selectedTags.has(String(item).trim()))
  }
  return true
}

async function openNodePicker(mode: NodePickerMode = 'source') {
  await loadMetadata()
  nodePickerMode.value = mode
  nodeSelectionDraft.value = mode === 'strategy' ? [...strategyNodeIds.value] : [...nodeIds.value]
  nodePickerVisible.value = true
  await loadNodeOptions()
}

function toggleNodeDraft(nodeId: number, checked: boolean) {
  if (checked && !nodeSelectionDraft.value.includes(nodeId)) {
    nodeSelectionDraft.value.push(nodeId)
  } else if (!checked) {
    nodeSelectionDraft.value = nodeSelectionDraft.value.filter((item) => item !== nodeId)
  }
}

function handleNodeDraftChange(nodeId: number, checked: boolean | string | number) {
  toggleNodeDraft(nodeId, Boolean(checked))
}

function confirmNodeSelection() {
  if (nodePickerMode.value === 'strategy') {
    strategyNodeIds.value = [...nodeSelectionDraft.value]
    nodePickerVisible.value = false
    return
  }
  nodeIds.value = [...nodeSelectionDraft.value]
  form.source_mode = 'manual'
  pruneStrategyNodesToManualSource()
  creationMode.value = 'manual'
  selectedPresetKey.value = ''
  nodePickerVisible.value = false
}

function removeSelectedNode(nodeId: number) {
  nodeIds.value = nodeIds.value.filter((item) => item !== nodeId)
  nodeSelectionDraft.value = nodeSelectionDraft.value.filter((item) => item !== nodeId)
  strategyNodeIds.value = strategyNodeIds.value.filter((item) => item !== nodeId)
}

function moveSelectedNode(index: number, direction: -1 | 1) {
  const nextIndex = index + direction
  if (nextIndex < 0 || nextIndex >= nodeIds.value.length) return
  const next = [...nodeIds.value]
  const [item] = next.splice(index, 1)
  next.splice(nextIndex, 0, item)
  nodeIds.value = next
  nodeSelectionDraft.value = [...next]
}

function clearSelectedNodes() {
  clearManualNodes()
}

function removeStrategyNode(nodeId: number) {
  strategyNodeIds.value = strategyNodeIds.value.filter((item) => item !== nodeId)
  if (nodePickerMode.value === 'strategy') {
    nodeSelectionDraft.value = nodeSelectionDraft.value.filter((item) => item !== nodeId)
  }
}

function moveStrategyNode(index: number, direction: -1 | 1) {
  const nextIndex = index + direction
  if (nextIndex < 0 || nextIndex >= strategyNodeIds.value.length) return
  const next = [...strategyNodeIds.value]
  const [item] = next.splice(index, 1)
  next.splice(nextIndex, 0, item)
  strategyNodeIds.value = next
  if (nodePickerMode.value === 'strategy') nodeSelectionDraft.value = [...next]
}

function nodeLabelById(nodeId: number) {
  const node = nodeOptions.value.find((item) => item.id === nodeId) || nodeCache.value[nodeId]
  return node ? `${node.name} #${node.id}` : `#${nodeId}`
}

async function startProxy(row: SmartProxy) {
  const { data } = await http.post(`/smart-proxies/${row.id}/start`)
  notifyRuntimeApply(data.runtime_apply_error, '已启动并自动应用到 Mihomo')
  await load()
}

async function stopProxy(row: SmartProxy) {
  const { data } = await http.post(`/smart-proxies/${row.id}/stop`)
  notifyRuntimeApply(data.runtime_apply_error, '已停止并自动应用到 Mihomo')
  await load()
}

async function deleteProxy(row: SmartProxy) {
  await ElMessageBox.confirm(`确定删除 ${row.name}？`, '删除代理', { type: 'warning' })
  await http.delete(`/smart-proxies/${row.id}`)
  ElMessage.success('已删除并自动应用到 Mihomo')
  await load()
}

async function reloadRuntime(reloadCore: boolean) {
  reloading.value = true
  try {
    const includeContent = !reloadCore
    const { data } = await http.post('/smart-proxies/reload', null, {
      params: { reload_core: reloadCore, include_content: includeContent },
    })
    if (includeContent) {
      runtimeContent.value = data.content || ''
      runtimeVisible.value = true
    }
    if (reloadCore && data.error) ElMessage.warning(data.error)
    else ElMessage.success(reloadCore ? '已重新应用到 Mihomo' : '已生成配置')
    if (reloadCore) await load()
  } finally {
    reloading.value = false
  }
}

async function enforceAccess() {
  enforcingAccess.value = true
  try {
    const { data } = await http.post('/smart-proxies/access/enforce')
    ElMessage.success(`访问检查完成，关闭 ${data.closed_connections || 0} 个未授权连接`)
    await refreshCoreStatus()
  } finally {
    enforcingAccess.value = false
  }
}

async function openGlobalConfig() {
  await loadGlobalConfig()
  globalConfigVisible.value = true
}

async function saveGlobalConfig() {
  const payload = {
    smart_proxy_auto_apply_interval_minutes: globalConfig.smart_proxy_auto_apply_interval_minutes,
    smart_proxy_monitor_interval_minutes: globalConfig.smart_proxy_monitor_interval_minutes,
    mihomo_runtime_config_path: globalConfig.mihomo_runtime_config_path,
    mihomo_core_config_path: globalConfig.mihomo_core_config_path,
    traffic_guard_enabled: globalConfig.traffic_guard_enabled,
    min_remaining_mb: globalConfig.min_remaining_mb,
    low_remaining_mb: globalConfig.low_remaining_mb,
    expire_soon_days: globalConfig.expire_soon_days,
    exclude_unknown_traffic: globalConfig.exclude_unknown_traffic,
  }
  const { data } = await http.put('/smart-proxies/config/global', payload)
  notifyRuntimeApply(data.runtime_apply_error, '全局配置已保存并自动应用到 Mihomo')
  globalConfigVisible.value = false
  await load()
}

async function loadProxyStatus(row: SmartProxy) {
  const { data } = await http.get(`/smart-proxies/${row.id}/status`, { params: { delay: true } })
  selectedStatus.value = data
  const target = items.value.find((item) => item.id === row.id)
  if (target) {
    target.status = data.status
    target.current_node = data.current_node
    target.switch_count = data.switch_count
    target.candidate_nodes = data.candidate_nodes
  }
  return data as SmartProxyStatus
}

async function showSwitchLogs(row: SmartProxy) {
  selectedSwitchProxy.value = row
  const { data } = await http.get(`/smart-proxies/${row.id}/switch-logs`, { params: { limit: 100 } })
  switchLogs.value = data
  switchLogsVisible.value = true
}

function openDiagnosis(row: SmartProxy) {
  selectedDiagnosisProxy.value = row
  selectedStatus.value = null
  selectedHealth.value = null
  healthLogs.value = []
  healthLogsVisible.value = false
  diagnosisMode.value = null
  healthVisible.value = true
}

async function loadProxyHealth(row: SmartProxy) {
  const { data } = await http.post(`/smart-proxies/${row.id}/health-check`, null, {
    params: { timeout_ms: 10000, scenario_checks: true },
  })
  selectedHealth.value = data
  await loadHealthLogs(row.id)
  await load()
}

async function runDiagnosis(mode: 'status' | 'health' | 'all') {
  const row = selectedDiagnosisProxy.value
  if (!row) return
  checkingId.value = row.id
  diagnosisMode.value = mode
  try {
    if (mode === 'status') {
      await loadProxyStatus(row)
      return
    }
    if (mode === 'health') {
      await loadProxyHealth(row)
      return
    }
    await loadProxyStatus(row)
    await loadProxyHealth(row)
  } finally {
    checkingId.value = null
    diagnosisMode.value = null
  }
}

async function loadHealthLogs(proxyId: number) {
  const { data } = await http.get(`/smart-proxies/${proxyId}/health-logs`, { params: { limit: 50 } })
  healthLogs.value = data
}

function formatDelay(value?: number | null) {
  return value === null || value === undefined ? '-' : `${value} ms`
}

function formatBytes(value?: number | null) {
  const bytes = Number(value || 0)
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB', 'PB']
  let size = bytes / 1024
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }
  return `${size.toFixed(size >= 100 ? 0 : size >= 10 ? 1 : 2)} ${units[unitIndex]}`
}

function formatRate(value?: number | null) {
  return `${formatBytes(value)}/s`
}

function statusTag(value?: string | null) {
  if (value === 'running' || value === 'ok' || value === 'online' || value === 'healthy') return 'success'
  if (value === 'stopped' || value === 'configured' || value === 'unknown') return 'info'
  if (value === 'degraded' || value === 'core_unavailable' || value === 'failed') return 'danger'
  return 'warning'
}

async function copy(value: string) {
  try {
    await copyText(value)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

onMounted(() => {
  load()
  connectStatusSocket()
})

onBeforeUnmount(() => {
  stopStatusSocket()
})
</script>

<style scoped>
.smart-proxy-mode {
  margin-bottom: 14px;
}

.proxy-dialog-tabs {
  min-height: 520px;
}

.proxy-dialog-tabs :deep(.el-tabs__content) {
  padding-top: 4px;
}

.smart-proxy-form :deep(.el-form-item__label) {
  font-weight: 600;
}

.switch-form-item :deep(.el-form-item__content) {
  min-height: 32px;
  align-items: center;
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.preset-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  min-height: 128px;
  padding: 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
}

.preset-card:hover,
.preset-card.active {
  border-color: var(--el-color-primary);
}

.preset-card.active {
  background: var(--el-color-primary-light-9);
}

.preset-title {
  font-weight: 650;
}

.preset-desc {
  flex: 1;
  color: var(--el-text-color-secondary);
  line-height: 1.45;
}

.preset-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.endpoint-list {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 7px;
  align-items: center;
  justify-content: center;
}

.endpoint-row {
  display: grid;
  grid-template-columns: auto minmax(120px, 1fr) 28px;
  align-items: center;
  gap: 8px;
  width: min(100%, 380px);
  min-height: 32px;
  padding: 3px 5px 3px 8px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color);
  border-radius: 999px;
}

.endpoint-tag {
  width: 72px;
  justify-content: center;
  border-radius: 999px;
}

.endpoint-text {
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-family: "JetBrains Mono", "Fira Code", Consolas, monospace;
  font-size: 12px;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.endpoint-copy {
  width: 24px;
  height: 24px;
  min-height: 24px;
}

.diagnosis-section-title {
  margin-bottom: 10px;
}

.diagnosis-section-title h3 {
  margin: 0;
  font-size: 15px;
}

.diagnosis-guide {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.diagnosis-guide strong {
  display: block;
  margin-bottom: 4px;
}

.diagnosis-guide p {
  margin: 0;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.diagnosis-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.diagnosis-log-entry {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.strategy-panel {
  margin: 0 0 14px;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.strategy-panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.strategy-panel p {
  margin: 0;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.strategy-panel .strategy-source-note {
  margin-top: 6px;
  color: var(--el-color-primary);
}

.strategy-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.node-selection,
.node-picker-toolbar,
.selected-node-list {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.node-count {
  color: var(--el-text-color-secondary);
}

.selected-node-list {
  margin-top: 10px;
}

.selected-node-list.ordered {
  align-items: stretch;
  flex-direction: column;
}

.selected-node-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.node-order {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.node-picker-toolbar {
  margin-bottom: 12px;
}

.node-picker-toolbar .el-input,
.node-picker-toolbar .el-select {
  width: 220px;
}

.picker-selected {
  min-height: 32px;
}

.label-with-help {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.help-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 50%;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1;
  cursor: help;
}

.strategy-help {
  display: grid;
  gap: 10px;
}

.strategy-help-item,
.strategy-option {
  display: grid;
  gap: 3px;
}

.strategy-help-item span,
.strategy-option small {
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
</style>
