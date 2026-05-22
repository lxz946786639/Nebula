<template>
  <section class="surface list-page">
    <div class="toolbar">
      <div class="toolbar-actions smart-proxy-toolbar-actions">
        <el-button type="primary" :icon="Plus" @click="openCreate">
          <span class="toolbar-label-full">新增代理</span>
          <span class="toolbar-label-short">新增</span>
        </el-button>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button :icon="Setting" @click="openGlobalConfig">
          <span class="toolbar-label-full">全局配置</span>
          <span class="toolbar-label-short">配置</span>
        </el-button>
        <el-button type="success" :icon="Switch" :loading="reloading" title="重新生成全部智能代理配置并热重载 Mihomo" @click="confirmReloadRuntime">
          <span class="toolbar-label-full">应用到 Mihomo</span>
          <span class="toolbar-label-short">应用</span>
        </el-button>
        <el-button :icon="DataAnalysis" :loading="reloading" title="预览即将写入 Mihomo 的 Runtime 配置" @click="reloadRuntime(false)">
          <span class="toolbar-label-full">预览配置</span>
          <span class="toolbar-label-short">预览</span>
        </el-button>
        <el-button :icon="Lock" :loading="enforcingAccess" @click="enforceAccess">
          <span class="toolbar-label-full">访问检查</span>
          <span class="toolbar-label-short">检查</span>
        </el-button>
      </div>
    </div>
    <el-descriptions class="desktop-summary" :column="4" border style="margin-bottom: 14px">
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
    <div class="mobile-summary-grid">
      <div class="mobile-summary-item">
        <span>Mihomo</span>
        <strong>{{ coreStatusText(coreStatus.available) }}</strong>
      </div>
      <div class="mobile-summary-item">
        <span>连接</span>
        <strong>{{ coreStatus.active_connections }}</strong>
      </div>
      <div class="mobile-summary-item">
        <span>上传</span>
        <strong>{{ formatRate(coreStatus.upload_speed) }}</strong>
      </div>
      <div class="mobile-summary-item">
        <span>下载</span>
        <strong>{{ formatRate(coreStatus.download_speed) }}</strong>
      </div>
    </div>
    <div class="table-wrap has-cards desktop-table">
      <el-table class="list-table" :data="items" stripe height="100%" empty-text="暂无代理服务">
      <el-table-column label="代理名称" min-width="190" class-name="table-cell-center">
        <template #default="{ row }">
          <div class="proxy-name-cell">
            <strong>{{ row.name }}</strong>
            <el-tag size="small" :type="runtimeStatusTag(row)" effect="plain">{{ runtimeStatusLabel(row) }}</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="100">
        <template #default="{ row }">{{ typeLabel(row.proxy_type) }}</template>
      </el-table-column>
      <el-table-column label="策略" width="120">
        <template #default="{ row }">{{ strategyLabel(row.strategy, row.stability_priority) }}</template>
      </el-table-column>
      <el-table-column label="数据来源" width="132">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ dataSourceSummary(row) }}</el-tag>
        </template>
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
      <el-table-column label="当前节点" min-width="210" class-name="table-cell-center">
        <template #default="{ row }">
          <div class="current-node-cell">
            <span>{{ row.current_node || '-' }}</span>
            <el-button link type="primary" title="查看节点调试历史" @click="showSwitchLogs(row)">
              节点调试历史（{{ row.switch_count }}）
            </el-button>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="应用" width="110">
        <template #default="{ row }">
          <el-tooltip :content="applyStatusReason(row)" placement="top">
            <el-tag :type="applyStatusType(row)">{{ applyStatusLabel(row) }}</el-tag>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="148" fixed="right" class-name="table-cell-actions" header-class-name="table-cell-actions">
        <template #default="{ row }">
          <div class="table-action-icons">
            <el-button :icon="Edit" circle title="编辑代理" @click="openEdit(row)" />
            <el-button
              type="primary"
              :icon="DataAnalysis"
              circle
              title="查看运行状态并执行健康检测"
              @click="openDiagnosis(row)"
            />
            <el-button
              v-if="row.enabled"
              type="warning"
              :icon="VideoPause"
              circle
              title="停止代理"
              @click="stopProxy(row)"
            />
            <el-button
              v-else
              type="success"
              :icon="VideoPlay"
              circle
              title="启动代理"
              @click="startProxy(row)"
            />
            <el-button type="danger" :icon="Delete" circle title="删除代理" @click="deleteProxy(row)" />
          </div>
        </template>
      </el-table-column>
      </el-table>
    </div>
    <div class="mobile-card-list data-cards">
      <el-empty v-if="!items.length" description="暂无代理服务" :image-size="72" />
      <article v-for="row in items" v-else :key="row.id" class="mobile-card smart-proxy-mobile-card">
        <div class="mobile-card-head">
          <div class="mobile-card-title">
            <strong>{{ row.name }}</strong>
            <span>智能代理服务</span>
          </div>
          <el-tag :type="runtimeStatusTag(row)" effect="plain">{{ runtimeStatusLabel(row) }}</el-tag>
        </div>

        <div class="smart-proxy-mobile-summary">
          <div class="smart-proxy-mobile-summary-item">
            <span>类型</span>
            <strong>{{ typeLabel(row.proxy_type) }}</strong>
          </div>
          <div class="smart-proxy-mobile-summary-item">
            <span>策略</span>
            <strong>{{ strategyLabel(row.strategy, row.stability_priority) }}</strong>
          </div>
          <div class="smart-proxy-mobile-summary-item">
            <span>数据来源</span>
            <el-tag size="small" effect="plain">{{ dataSourceSummary(row) }}</el-tag>
          </div>
          <div class="smart-proxy-mobile-summary-item">
            <span>应用</span>
            <el-tag size="small" :type="applyStatusType(row)" effect="plain">{{ applyStatusLabel(row) }}</el-tag>
          </div>
        </div>

        <section class="smart-proxy-mobile-section">
          <div class="smart-proxy-mobile-section-head">代理地址</div>
          <div class="endpoint-list mobile-endpoint-list">
            <div v-for="endpoint in endpointOptions(row)" :key="endpoint.scheme" class="endpoint-row">
              <el-tag class="endpoint-tag" size="small" effect="plain">{{ endpoint.label }}</el-tag>
              <span class="endpoint-text">{{ endpoint.url }}</span>
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
        </section>

        <section class="smart-proxy-mobile-section smart-proxy-mobile-current">
          <div class="smart-proxy-mobile-current-copy">
            <span>当前节点</span>
            <strong>{{ row.current_node || '-' }}</strong>
          </div>
          <el-button link type="primary" title="查看节点调试历史" @click="showSwitchLogs(row)">
            节点调试历史（{{ row.switch_count }}）
          </el-button>
        </section>

        <dl class="mobile-kv smart-proxy-mobile-note">
          <div>
            <dt>说明</dt>
            <dd>{{ applyStatusReason(row) }}</dd>
          </div>
        </dl>

        <div class="mobile-card-actions">
          <el-button :icon="Edit" @click="openEdit(row)">编辑</el-button>
          <el-button :icon="DataAnalysis" @click="openDiagnosis(row)">诊断</el-button>
          <el-button v-if="row.enabled" :icon="VideoPause" type="warning" @click="stopProxy(row)">停用</el-button>
          <el-button v-else :icon="VideoPlay" type="success" @click="startProxy(row)">启用</el-button>
          <el-button :icon="Delete" type="danger" @click="deleteProxy(row)">删除</el-button>
        </div>
      </article>
    </div>
  </section>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="980px" class="smart-proxy-dialog">
    <div v-if="!editingId && createWizardStep !== 'form'" class="create-wizard">
      <ol class="wizard-stepper">
        <li :class="{ active: createWizardStep === 'method', done: createWizardStep !== 'method' }">
          <span class="wizard-step-index">1</span>
          <span class="wizard-step-text">选择方式</span>
        </li>
        <li :class="{ active: createWizardStep === 'preset' }">
          <span class="wizard-step-index">2</span>
          <span class="wizard-step-text">{{ creationMode === 'quick' ? '选择模板' : '填写配置' }}</span>
        </li>
        <li v-if="creationMode === 'quick'">
          <span class="wizard-step-index">3</span>
          <span class="wizard-step-text">填写配置</span>
        </li>
      </ol>

      <section v-if="createWizardStep === 'method'" class="wizard-section">
        <div class="wizard-section-head">
          <div>
            <em>STEP 1</em>
            <strong>选择新增方式</strong>
          </div>
          <span>按当前使用场景选择入口，后续表单会保留对应的必要配置。</span>
        </div>
        <div class="wizard-option-grid">
          <button
            v-for="option in createModeOptions"
            :key="option.value"
            type="button"
            class="wizard-option-card"
            @click="startCreateMode(option.value)"
          >
            <span class="wizard-option-head">
              <span class="wizard-option-title">{{ option.title }}</span>
              <span class="wizard-option-arrow">选择</span>
            </span>
            <span class="wizard-option-desc">{{ option.description }}</span>
            <span class="wizard-option-meta">
              <el-tag v-for="tag in option.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
            </span>
          </button>
        </div>
      </section>

      <section v-else class="wizard-section">
        <div class="wizard-section-head">
          <div>
            <em>STEP 2</em>
            <strong>选择快速模板</strong>
          </div>
          <span>默认使用自定义模板，也可以选择一个场景模板后再进入表单微调。</span>
        </div>
        <div class="preset-grid wizard-preset-grid">
          <button
            v-for="preset in quickPresetCards"
            :key="preset.key"
            type="button"
            class="preset-card"
            :class="{ active: selectedPresetKey === preset.key }"
            @click="selectPreset(preset)"
          >
            <span class="preset-title">{{ preset.name }}</span>
            <span class="preset-desc">{{ preset.description }}</span>
            <span class="preset-meta">
              <el-tag size="small" effect="plain">{{ strategyLabel(preset.strategy) }}</el-tag>
              <el-tag size="small" effect="plain">{{ scenarioLabel(preset.scenario) }}</el-tag>
            </span>
          </button>
        </div>
      </section>
    </div>

    <el-form v-else label-position="top" class="smart-proxy-form">
      <div v-if="!editingId" class="create-form-summary">
        <div>
          <strong>{{ createModeLabel(creationMode) }}</strong>
          <span>{{ createModeSummary }}</span>
        </div>
        <el-button class="summary-back-button" plain type="primary" @click="goBackInCreateWizard">返回上一步</el-button>
      </div>
      <el-tabs v-model="activeDialogTab" class="proxy-dialog-tabs">
        <el-tab-pane label="基础配置" name="basic">
          <div class="form-grid">
            <el-form-item label="代理名称" required :error="proxyNameError">
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
            <el-form-item label="数据来源" required>
              <el-select v-model="form.data_source" @change="onDataSourceChange">
                <el-option label="订阅节点" value="subscription" />
                <el-option label="蚂蚁节点" value="ant" />
              </el-select>
            </el-form-item>
            <el-form-item label="节点来源" required>
              <el-select v-model="form.source_mode" @change="onSourceModeChange">
                <el-option
                  v-for="option in sourceModeOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="isAntSource || form.source_mode === 'country'"
              :label="isAntSource ? '指定地区' : '国家/地区'"
              :required="!isAntSource"
            >
              <el-select
                v-model="countryCodes"
                multiple
                filterable
                allow-create
                default-first-option
                clearable
                :placeholder="isAntSource ? '不选择则不限地区' : '选择或输入国家代码'"
                @change="onSourceFilterChange"
              >
                <el-option
                  v-for="country in currentCountryOptions"
                  :key="country.code"
                  :label="countryOptionLabel(country)"
                  :value="country.code"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="isAntSource || form.source_mode === 'tag'"
              :label="isAntSource ? '指定线路' : tagFilterLabel"
              :required="!isAntSource"
            >
              <el-select
                v-model="tags"
                multiple
                filterable
                allow-create
                default-first-option
                clearable
                :placeholder="isAntSource ? '不选择则不限线路' : '选择或输入标签'"
                @change="onSourceFilterChange"
              >
                <el-option
                  v-for="tag in currentTagOptions"
                  :key="tag.value"
                  :label="tag.label"
                  :value="tag.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.data_source === 'subscription' && form.source_mode === 'subscription'" label="订阅来源" required>
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
                :placeholder="protocolPlaceholder"
                @change="onSourceFilterChange"
              >
                <el-option v-for="protocol in currentProtocolOptions" :key="protocol" :label="protocol" :value="protocol" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item v-if="form.source_mode === 'manual'" label="指定节点来源" required>
            <div class="node-selection">
              <el-button :icon="Plus" @click="openNodePicker('source')">选择节点</el-button>
              <el-button v-if="selectedManualNodeIds.length" @click="clearSelectedNodes">清空</el-button>
              <span class="node-count">已选 {{ selectedManualNodeIds.length }} 个节点</span>
            </div>
            <div v-if="selectedManualNodeIds.length" class="selected-node-list">
              <div v-for="nodeId in selectedManualNodeIds" :key="nodeId" class="selected-node-item">
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
              <el-button v-if="selectedStrategyNodeIds.length" @click="clearStrategyNodes">清空</el-button>
              <span class="node-count">
                {{ selectedStrategyNodeIds.length ? `已选 ${selectedStrategyNodeIds.length} 个策略节点` : '未选择时使用基础配置中的全部候选节点' }}
              </span>
            </div>
            <div v-if="selectedStrategyNodeIds.length" class="selected-node-list" :class="{ ordered: strategyUsesOrder }">
              <div v-for="(nodeId, index) in selectedStrategyNodeIds" :key="nodeId" class="selected-node-item">
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
                    :disabled="index === selectedStrategyNodeIds.length - 1"
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
      <div class="smart-proxy-dialog-footer">
        <template v-if="!editingId && createWizardStep === 'method'">
          <el-button @click="dialogVisible = false">取消</el-button>
        </template>
        <template v-else-if="!editingId && createWizardStep === 'preset'">
          <el-button @click="goBackInCreateWizard">上一步</el-button>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :disabled="!selectedPresetKey" @click="continueFromPreset">下一步</el-button>
        </template>
        <template v-else>
          <el-button v-if="!editingId" @click="goBackInCreateWizard">上一步</el-button>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="save">保存</el-button>
        </template>
      </div>
    </template>
  </el-dialog>

  <el-dialog v-model="nodePickerVisible" class="node-picker-dialog" :title="nodePickerTitle" width="980px">
    <div class="node-picker-toolbar">
      <el-input v-model="nodeQ" placeholder="搜索节点/服务器/来源" clearable @change="loadNodeOptions" />
      <el-select v-model="nodeCountry" filterable clearable placeholder="国家/地区" @change="loadNodeOptions">
        <el-option
          v-for="country in currentCountryOptions"
          :key="country.code"
          :label="countryOptionLabel(country)"
          :value="country.code"
        />
      </el-select>
      <el-input v-model="nodeGroup" :placeholder="nodeGroupPlaceholder" clearable @change="loadNodeOptions" />
      <el-button :icon="Refresh" :loading="nodePickerLoading" @click="loadNodeOptions">刷新</el-button>
    </div>
    <el-table class="node-picker-table" :data="nodeOptions" stripe height="420" empty-text="暂无可选节点">
      <el-table-column width="54">
        <template #default="{ row }">
          <el-checkbox
            :model-value="nodeSelectionDraft.includes(row.id)"
            @change="handleNodeDraftChange(row.id, $event)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="name" label="节点" min-width="260" show-overflow-tooltip class-name="table-cell-left" />
      <el-table-column prop="source_subscription_name" :label="nodeSourceColumnLabel" min-width="130" show-overflow-tooltip class-name="table-cell-left" />
      <el-table-column prop="type" label="协议" width="90" />
      <el-table-column prop="country_code" label="国家" width="90" />
      <el-table-column label="延迟" width="110">
        <template #default="{ row }">{{ formatDelay(row.latency) }}</template>
      </el-table-column>
      <el-table-column prop="server" label="服务器" min-width="180" show-overflow-tooltip class-name="table-cell-left" />
    </el-table>
    <div class="node-picker-mobile-list">
      <el-empty v-if="!nodeOptions.length && !nodePickerLoading" description="暂无可选节点" :image-size="72" />
      <article
        v-for="node in nodeOptions"
        :key="node.id"
        class="node-picker-card"
        :class="{ 'is-selected': nodeSelectionDraft.includes(node.id) }"
        @click="toggleNodeDraft(node.id, !nodeSelectionDraft.includes(node.id))"
      >
        <div class="node-picker-card-head">
          <el-checkbox
            :model-value="nodeSelectionDraft.includes(node.id)"
            @click.stop
            @change="handleNodeDraftChange(node.id, $event)"
          />
          <div class="node-picker-card-title">
            <strong>{{ node.name }}</strong>
            <span>{{ node.source_subscription_name || '-' }}</span>
          </div>
          <el-tag size="small" effect="plain">{{ node.country_code || '-' }}</el-tag>
        </div>
        <dl class="node-picker-card-meta">
          <div>
            <dt>协议</dt>
            <dd>{{ node.type || '-' }}</dd>
          </div>
          <div>
            <dt>延迟</dt>
            <dd>{{ formatDelay(node.latency) }}</dd>
          </div>
          <div class="is-wide">
            <dt>服务器</dt>
            <dd>{{ node.server || '-' }}</dd>
          </div>
        </dl>
      </article>
    </div>
    <div class="picker-selected">
      <div class="picker-selected-head">
        <span>已选节点</span>
        <strong>{{ nodeSelectionDraft.length }}</strong>
      </div>
      <div class="selected-node-list picker-selected-tags" :class="{ 'is-empty': !nodeSelectionDraft.length }">
        <span v-if="!nodeSelectionDraft.length" class="picker-selected-empty">暂无选择</span>
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
              自动应用间隔（分钟）
              <el-popover placement="top" width="360" trigger="hover">
                <template #reference>
                  <span class="help-icon" title="0 表示关闭，开启后按需应用到 Mihomo">?</span>
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

  <el-dialog v-model="healthVisible" class="diagnosis-dialog" :title="`代理诊断${selectedDiagnosisProxy ? ` - ${selectedDiagnosisProxy.name}` : ''}`" width="920px">
    <div class="diagnosis-dialog-content">
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
        <el-descriptions class="diagnosis-desktop-block" :column="3" border style="margin-bottom: 14px">
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
        <div class="diagnosis-mobile-grid diagnosis-mobile-only">
          <div v-for="item in runtimeDiagnosisItems" :key="item.label" class="diagnosis-kv-card" :class="{ 'is-wide': item.wide }">
            <span>{{ item.label }}</span>
            <div class="diagnosis-kv-value">
              <strong>{{ item.value }}</strong>
              <el-tag v-if="item.badgeText" :type="item.tagType" effect="plain">{{ item.badgeText }}</el-tag>
            </div>
          </div>
        </div>
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
        <el-descriptions class="diagnosis-desktop-block" :column="3" border style="margin-bottom: 14px">
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
        <div class="diagnosis-mobile-grid diagnosis-mobile-only">
          <div v-for="item in healthDiagnosisItems" :key="item.label" class="diagnosis-kv-card" :class="{ 'is-wide': item.wide }">
            <span>{{ item.label }}</span>
            <div class="diagnosis-kv-value">
              <strong>{{ item.value }}</strong>
              <el-tag v-if="item.badgeText" :type="item.tagType" effect="plain">{{ item.badgeText }}</el-tag>
            </div>
          </div>
        </div>
        <el-table class="diagnosis-desktop-block" :data="selectedHealth.checks" stripe max-height="220" style="margin-bottom: 14px">
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
        <div class="diagnosis-mobile-list diagnosis-mobile-only">
          <article v-for="check in selectedHealth.checks" :key="check.check_type" class="diagnosis-result-card">
            <div class="diagnosis-result-head">
              <strong>{{ checkTypeText(check.check_type) }}</strong>
              <el-tag :type="statusTag(check.status)" effect="plain">{{ readableStatusText(check.status) }}</el-tag>
            </div>
            <dl class="diagnosis-card-kv">
              <div>
                <dt>延迟</dt>
                <dd>{{ formatDelay(check.delay) }}</dd>
              </div>
              <div>
                <dt>说明</dt>
                <dd>{{ statusMessageText(check.message) }}</dd>
              </div>
            </dl>
          </article>
        </div>
        <el-table class="diagnosis-desktop-block" :data="selectedHealth.nodes" stripe max-height="320">
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
        <div class="diagnosis-mobile-list diagnosis-mobile-only">
          <article v-for="node in selectedHealth.nodes" :key="`${node.node_id || node.name}-${node.source || ''}`" class="diagnosis-result-card">
            <div class="diagnosis-result-head">
              <strong>{{ node.name }}</strong>
              <el-tag :type="statusTag(node.status)" effect="plain">{{ readableStatusText(node.status) }}</el-tag>
            </div>
            <dl class="diagnosis-card-kv">
              <div>
                <dt>来源</dt>
                <dd>{{ node.source || '-' }}</dd>
              </div>
              <div>
                <dt>协议</dt>
                <dd>{{ node.type || '-' }}</dd>
              </div>
              <div>
                <dt>延迟</dt>
                <dd>{{ formatDelay(node.delay) }}</dd>
              </div>
              <div>
                <dt>当前</dt>
                <dd>{{ node.current ? '是' : '-' }}</dd>
              </div>
            </dl>
          </article>
        </div>
        <div class="diagnosis-log-entry">
          <el-button :icon="DataAnalysis" @click="healthLogsVisible = true">
            查看最近检测日志（{{ healthLogs.length }}）
          </el-button>
        </div>
      </template>
    </div>
    <template #footer>
      <el-button @click="healthVisible = false">关闭</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="healthLogsVisible" class="health-logs-dialog" title="最近检测日志" width="860px">
    <el-table class="diagnosis-desktop-block" :data="healthLogs" stripe max-height="460" empty-text="暂无检测日志">
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
    <div class="diagnosis-mobile-list diagnosis-mobile-only">
      <el-empty v-if="!healthLogs.length" description="暂无检测日志" :image-size="72" />
      <article v-for="log in healthLogs" :key="log.id" class="diagnosis-result-card">
        <div class="diagnosis-result-head">
          <strong>{{ checkTypeText(log.check_type) }}</strong>
          <el-tag :type="statusTag(log.status)" effect="plain">{{ readableStatusText(log.status) }}</el-tag>
        </div>
        <dl class="diagnosis-card-kv">
          <div>
            <dt>时间</dt>
            <dd>{{ formatDateTime(log.created_at) }}</dd>
          </div>
          <div>
            <dt>节点</dt>
            <dd>{{ log.node_name || '-' }}</dd>
          </div>
          <div>
            <dt>延迟</dt>
            <dd>{{ formatDelay(log.latency) }}</dd>
          </div>
          <div>
            <dt>说明</dt>
            <dd>{{ statusMessageText(log.message) }}</dd>
          </div>
        </dl>
      </article>
    </div>
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
  data_source: 'subscription' | 'ant'
  source_mode: string
  subscription_ids: number[]
  country_codes: string[]
  tags: string[]
  node_ids: number[]
  strategy_node_ids: number[]
  ant_node_ids: string[]
  ant_strategy_node_ids: string[]
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
  data_source?: 'subscription' | 'ant'
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
  ant_loaded: boolean
  ant_countries: SmartProxyCountryOption[]
  ant_tags: Array<{ value: string; label: string; nodes: number }>
  ant_protocol_types: string[]
  presets: SmartProxyPreset[]
}

interface NodeItem {
  id: number | string
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
type NodeKey = number | string
type CreationMode = 'quick' | 'advanced' | 'manual'
type CreateWizardStep = 'method' | 'preset' | 'form'

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

interface DiagnosisDisplayItem {
  label: string
  value: string
  badgeText?: string
  tagType?: string
  wide?: boolean
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
const creationMode = ref<CreationMode>('quick')
const createWizardStep = ref<CreateWizardStep>('method')
const selectedPresetKey = ref('')
const formBaseline = ref('')
const countryCodes = ref<string[]>([])
const tags = ref<string[]>([])
const subscriptionIds = ref<number[]>([])
const nodeIds = ref<number[]>([])
const strategyNodeIds = ref<number[]>([])
const antNodeIds = ref<string[]>([])
const antStrategyNodeIds = ref<string[]>([])
const protocolTypes = ref<string[]>([])
const metadataLoaded = ref(false)
const metadata = reactive<SmartProxyMetadata>({
  countries: [],
  subscriptions: [],
  tags: [],
  protocol_types: [],
  ant_loaded: false,
  ant_countries: [],
  ant_tags: [],
  ant_protocol_types: [],
  presets: [],
})
const nodePickerVisible = ref(false)
const nodePickerLoading = ref(false)
const nodeOptions = ref<NodeItem[]>([])
const nodeSelectionDraft = ref<NodeKey[]>([])
const nodePickerMode = ref<NodePickerMode>('source')
const nodeCache = ref<Record<string, NodeItem>>({})
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
  data_source: 'subscription' as 'subscription' | 'ant',
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
const CUSTOM_PRESET_KEY = 'custom'
const customPreset: SmartProxyPreset = {
  key: CUSTOM_PRESET_KEY,
  name: '自定义',
  description: '从空白配置开始，自行选择策略、来源和过滤条件。',
  proxy_type: 'mixed',
  strategy: 'fallback',
  stability_priority: false,
  scenario: 'general',
  data_source: 'subscription',
  source_mode: 'all',
  country_codes: [],
  tags: [],
  protocol_types: [],
  health_check_url: 'http://www.gstatic.com/generate_204',
  health_check_interval: 300,
  tolerance: 50,
}
const createModeOptions: Array<{ value: CreationMode; title: string; description: string; tags: string[] }> = [
  {
    value: 'quick',
    title: '快速模板',
    description: '先选一个常用场景模板，再进入表单做少量调整。',
    tags: ['推荐', '场景预设'],
  },
  {
    value: 'advanced',
    title: '高级编排',
    description: '从完整配置表单开始，适合自定义来源、策略和安全规则。',
    tags: ['完整配置', '策略编排'],
  },
  {
    value: 'manual',
    title: '手动选节点',
    description: '直接进入指定节点模式，手动挑选候选节点和策略节点。',
    tags: ['指定节点', '精确控制'],
  },
]
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
const isAntSource = computed(() => form.data_source === 'ant')
const selectedManualNodeIds = computed<NodeKey[]>(() => (isAntSource.value ? antNodeIds.value : nodeIds.value))
const selectedStrategyNodeIds = computed<NodeKey[]>(() => (isAntSource.value ? antStrategyNodeIds.value : strategyNodeIds.value))
const sourceModeOptions = computed(() =>
  isAntSource.value
    ? [
        { label: '所有蚂蚁节点', value: 'all' },
        { label: '指定节点', value: 'manual' },
      ]
    : [
        { label: '所有节点', value: 'all' },
        { label: '指定订阅', value: 'subscription' },
        { label: '指定国家', value: 'country' },
        { label: '指定标签', value: 'tag' },
        { label: '指定节点', value: 'manual' },
      ],
)
const currentCountryOptions = computed(() => (isAntSource.value ? metadata.ant_countries : metadata.countries))
const currentTagOptions = computed(() =>
  isAntSource.value
    ? metadata.ant_tags.filter((tag) => tag.value === 'line:free' || tag.value === 'line:paid')
    : metadata.tags.map((tag) => ({ value: tag, label: tag, nodes: 0 })),
)
const currentProtocolOptions = computed(() => (isAntSource.value ? metadata.ant_protocol_types : metadata.protocol_types))
const tagFilterLabel = computed(() => (isAntSource.value ? '线路' : '节点标签'))
const protocolPlaceholder = computed(() => (isAntSource.value ? '不选默认全部：ws / wss / tcp' : '不选默认全部：vmess / trojan / ss'))
const nodeGroupPlaceholder = computed(() => (isAntSource.value ? '线路' : '分组'))
const nodeSourceColumnLabel = computed(() => (isAntSource.value ? '线路' : '来源'))
const quickPresetCards = computed(() => [customPreset, ...metadata.presets])
const selectedQuickPreset = computed(() => quickPresetCards.value.find((item) => item.key === selectedPresetKey.value) || customPreset)
const dialogTitle = computed(() => {
  if (editingId.value) return '编辑代理'
  if (createWizardStep.value === 'preset') return '新增代理 - 选择快速模板'
  if (createWizardStep.value === 'form') return '新增代理 - 填写配置'
  return '新增代理'
})
const createModeSummary = computed(() => {
  if (creationMode.value === 'quick') return `快速模板：${selectedQuickPreset.value.name}`
  if (creationMode.value === 'manual') return '手动指定节点作为候选来源'
  return '完整表单配置策略、来源和访问控制'
})
const proxyNameError = computed(() => {
  const normalizedName = normalizeProxyName(form.name)
  if (!normalizedName) return ''
  const duplicated = items.value.some((item) => item.id !== editingId.value && normalizeProxyName(item.name) === normalizedName)
  return duplicated ? '代理名称已存在，请换一个名称' : ''
})
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
const runtimeDiagnosisItems = computed<DiagnosisDisplayItem[]>(() => {
  const status = selectedStatus.value
  if (!status) return []

  return [
    { label: '代理', value: status.name, badgeText: runtimeStatusText(status.status), tagType: statusTag(status.status), wide: true },
    { label: '当前节点', value: status.current_node || '-', wide: true },
    { label: '延迟', value: formatDelay(status.delay) },
    { label: '候选节点', value: `${status.candidate_nodes}` },
    { label: '运行节点', value: `${status.runtime_nodes}` },
    { label: '在线节点', value: `${status.online_nodes}` },
    { label: '失败节点', value: `${status.failed_nodes}` },
    { label: '平均延迟', value: formatDelay(status.average_delay) },
    { label: '最优节点', value: status.best_node || '-', wide: true },
    { label: '活动连接', value: `${status.active_connections}` },
    { label: '在线来源', value: `${status.online_users}` },
    { label: '上传速率', value: formatRate(status.upload_speed) },
    { label: '下载速率', value: formatRate(status.download_speed) },
    { label: '切换次数', value: `${status.switch_count}` },
    { label: '未授权连接', value: `${status.unauthorized_connections}` },
    { label: '流量保护', value: status.traffic_guard_enabled ? '开启' : '关闭' },
    { label: '流量排除', value: `${status.traffic_excluded_nodes}` },
    { label: '低流量风险', value: `${status.traffic_risk_nodes}` },
    { label: '流量快照', value: status.traffic_snapshot_at ? formatDateTime(status.traffic_snapshot_at) : '-', wide: true },
    { label: '策略组', value: status.group_name, wide: true },
    { label: '错误', value: statusMessageText(status.error), wide: true },
    { label: '来源 IP', value: status.source_ips.length ? status.source_ips.join(', ') : '-', wide: true },
  ]
})
const healthDiagnosisItems = computed<DiagnosisDisplayItem[]>(() => {
  const health = selectedHealth.value
  if (!health) return []

  return [
    { label: '代理', value: health.name, badgeText: readableStatusText(health.status), tagType: statusTag(health.status), wide: true },
    { label: '检测时间', value: formatDateTime(health.checked_at), wide: true },
    { label: '在线', value: `${health.online_nodes}/${health.total_nodes}` },
    { label: '平均延迟', value: formatDelay(health.average_delay) },
    { label: '最优节点', value: health.best_node || '-', wide: true },
    { label: '当前节点', value: health.current_node || '-', wide: true },
    { label: '错误', value: statusMessageText(health.error), wide: true },
  ]
})
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
    value: 'proxy_unavailable',
    label: '代理不可用',
    description: '代理已应用且策略组存在，但代理下所有运行节点当前都不可用。',
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

function normalizeProxyName(value: string | null | undefined) {
  return String(value || '').trim().toLowerCase()
}

function createModeLabel(value: CreationMode) {
  return createModeOptions.find((item) => item.value === value)?.title || '新增代理'
}

function formSnapshot() {
  return JSON.stringify({
    form: { ...form },
    creationMode: creationMode.value,
    selectedPresetKey: selectedPresetKey.value,
    countryCodes: [...countryCodes.value],
    tags: [...tags.value],
    subscriptionIds: [...subscriptionIds.value],
    nodeIds: [...nodeIds.value],
    strategyNodeIds: [...strategyNodeIds.value],
    antNodeIds: [...antNodeIds.value],
    antStrategyNodeIds: [...antStrategyNodeIds.value],
    protocolTypes: [...protocolTypes.value],
    ipWhitelistText: ipWhitelistText.value,
  })
}

function markFormPristine() {
  formBaseline.value = formSnapshot()
}

function hasDraftChanges() {
  return Boolean(formBaseline.value) && formSnapshot() !== formBaseline.value
}

async function confirmResetDraft(title = '切换配置') {
  if (!hasDraftChanges()) return true
  try {
    await ElMessageBox.confirm('返回后当前已填写的表单内容会重置，是否继续？', title, {
      type: 'warning',
      confirmButtonText: '继续切换',
      cancelButtonText: '取消',
      autofocus: false,
      customClass: 'smart-proxy-reset-confirm',
    })
    return true
  } catch {
    return false
  }
}

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
    data_source: 'subscription',
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
  createWizardStep.value = 'method'
  selectedPresetKey.value = ''
  countryCodes.value = []
  tags.value = []
  subscriptionIds.value = []
  nodeIds.value = []
  strategyNodeIds.value = []
  antNodeIds.value = []
  antStrategyNodeIds.value = []
  protocolTypes.value = []
  nodeSelectionDraft.value = []
  nodePickerMode.value = 'source'
  ipWhitelistText.value = ''
  editingId.value = null
  formBaseline.value = ''
}

function typeLabel(value: string) {
  if (value === 'socks') return 'SOCKS5'
  if (value === 'mixed') return '混合代理'
  return 'HTTP'
}

function dataSourceLabel(value?: string) {
  return value === 'ant' ? '蚂蚁节点' : '订阅节点'
}

function dataSourceSummary(row: SmartProxy) {
  return `${dataSourceLabel(row.data_source)}（${row.candidate_nodes}）`
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
    proxy_unavailable: '代理不可用',
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
    'No runtime nodes in Mihomo group': 'Mihomo 策略组中没有运行节点',
    'All proxy nodes are unavailable': '代理下所有节点当前不可用',
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
    if (['degraded', 'core_unavailable', 'proxy_unavailable'].includes(row.status) && row.last_error) return 'failed'
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
    pending: 'danger',
    failed: 'danger',
    disabled: 'danger',
  }
  return types[resolvedApplyStatus(row)] || 'danger'
}

function applyStatusReason(row: SmartProxy) {
  if (row.apply_status_reason) return statusMessageText(row.apply_status_reason)
  if (row.last_error) return statusMessageText(row.last_error)
  const reasons: Record<string, string> = {
    applied: '当前配置已成功应用到 Mihomo。',
    pending: '代理配置尚未应用到 Mihomo，请点击顶部“应用到 Mihomo”。',
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
  return '选择“仅保存”后，需要手动点击顶部“应用到 Mihomo”才会热重载。'
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

function nodeCacheKey(nodeId: NodeKey) {
  return String(nodeId)
}

function activeManualIds() {
  return isAntSource.value ? antNodeIds.value : nodeIds.value
}

function activeStrategyIds() {
  return isAntSource.value ? antStrategyNodeIds.value : strategyNodeIds.value
}

function setActiveManualIds(values: NodeKey[]) {
  if (isAntSource.value) {
    antNodeIds.value = values.map((item) => String(item))
  } else {
    nodeIds.value = values.map((item) => Number(item)).filter((item) => Number.isInteger(item))
  }
}

function setActiveStrategyIds(values: NodeKey[]) {
  if (isAntSource.value) {
    antStrategyNodeIds.value = values.map((item) => String(item))
  } else {
    strategyNodeIds.value = values.map((item) => Number(item)).filter((item) => Number.isInteger(item))
  }
}

function clearManualNodes() {
  if (isAntSource.value) antNodeIds.value = []
  else nodeIds.value = []
  nodeSelectionDraft.value = []
  if (form.source_mode === 'manual') setActiveStrategyIds([])
}

function clearStrategyNodes() {
  setActiveStrategyIds([])
  if (nodePickerMode.value === 'strategy') nodeSelectionDraft.value = []
}

function pruneStrategyNodesToManualSource() {
  const strategyIds = activeStrategyIds()
  if (form.source_mode !== 'manual' || !strategyIds.length) return
  const sourceIds = new Set(activeManualIds().map((item) => String(item)))
  setActiveStrategyIds(strategyIds.filter((item) => sourceIds.has(String(item))))
}

function clearSourceFiltersForMode(mode: string) {
  if (isAntSource.value) {
    subscriptionIds.value = []
    return
  }
  if (mode !== 'country') countryCodes.value = []
  if (mode !== 'tag') tags.value = []
  if (mode !== 'subscription') subscriptionIds.value = []
}

function onSourceFilterChange() {
  if (!activeStrategyIds().length) return
  setActiveStrategyIds([])
  ElMessage.info('节点来源筛选已变更，策略节点选择已清空')
}

function onSourceModeChange(value: string | number | boolean | undefined) {
  const mode = String(value || 'all')
  if (activeStrategyIds().length) {
    setActiveStrategyIds([])
    ElMessage.info('节点来源已变更，策略节点选择已清空')
  }
  if (isAntSource.value) {
    subscriptionIds.value = []
    if (mode === 'manual') {
      protocolTypes.value = []
      return
    }
    if (activeManualIds().length) {
      ElMessage.info('已切换为所有蚂蚁节点，手动选择的节点已清空')
      clearManualNodes()
    }
    return
  }
  if (mode === 'manual') {
    countryCodes.value = []
    tags.value = []
    subscriptionIds.value = []
    protocolTypes.value = []
  } else {
    if (activeManualIds().length) {
      ElMessage.info('已切换为筛选模式，手动选择的节点已清空')
      clearManualNodes()
    }
    clearSourceFiltersForMode(mode)
  }
}

function onDataSourceChange() {
  form.source_mode = 'all'
  countryCodes.value = []
  tags.value = []
  subscriptionIds.value = []
  protocolTypes.value = []
  nodeIds.value = []
  strategyNodeIds.value = []
  antNodeIds.value = []
  antStrategyNodeIds.value = []
  nodeSelectionDraft.value = []
  selectedPresetKey.value = ''
}

function validateStrategyBeforeSave() {
  if (isAntSource.value && !metadata.ant_loaded) {
    ElMessage.warning('请先在蚂蚁代理页登录 Ant 账号或上传 ant.db')
    return false
  }
  if (!isAntSource.value && form.source_mode === 'subscription' && subscriptionIds.value.length === 0) {
    ElMessage.warning('指定订阅模式请至少选择一个订阅来源')
    return false
  }
  if (!isAntSource.value && form.source_mode === 'country' && countryCodes.value.length === 0) {
    ElMessage.warning('指定国家模式请至少选择一个国家/地区')
    return false
  }
  if (!isAntSource.value && form.source_mode === 'tag' && tags.value.length === 0) {
    ElMessage.warning('指定标签模式请至少选择一个节点标签')
    return false
  }
  if (form.source_mode === 'manual' && activeStrategyIds().length) {
    const sourceIds = new Set(activeManualIds().map((item) => String(item)))
    if (activeStrategyIds().some((item) => !sourceIds.has(String(item)))) {
      ElMessage.warning('策略节点必须来自基础配置中的指定节点来源')
      return false
    }
  }
  const selectedStrategyCount = activeStrategyIds().length
  const knownCandidateCount = selectedStrategyCount || (form.source_mode === 'manual' ? activeManualIds().length : null)
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

function applyGlobalTrafficDefaultsToForm() {
  Object.assign(form, {
    traffic_guard_enabled: globalConfig.traffic_guard_enabled,
    min_remaining_mb: globalConfig.min_remaining_mb,
    low_remaining_mb: globalConfig.low_remaining_mb,
    expire_soon_days: globalConfig.expire_soon_days,
    exclude_unknown_traffic: globalConfig.exclude_unknown_traffic,
  })
}

function applyPreset(preset: SmartProxyPreset) {
  selectedPresetKey.value = preset.key
  Object.assign(form, {
    name: preset.key === CUSTOM_PRESET_KEY ? '' : preset.name,
    description: '',
    proxy_type: preset.proxy_type,
    strategy: preset.strategy,
    stability_priority: preset.strategy === 'stable',
    scenario: preset.scenario,
    data_source: preset.data_source || 'subscription',
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
  antNodeIds.value = []
  antStrategyNodeIds.value = []
}

function selectPreset(preset: SmartProxyPreset) {
  applyPreset(preset)
  markFormPristine()
}

function applyCreationMode(value: CreationMode) {
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
    antStrategyNodeIds.value = []
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
    antStrategyNodeIds.value = []
    protocolTypes.value = []
  } else if (value === 'quick') {
    applyPreset(customPreset)
  }
}

function prepareCreateDraft(mode: CreationMode, preset: SmartProxyPreset = customPreset) {
  resetForm()
  applyGlobalTrafficDefaultsToForm()
  creationMode.value = mode
  if (mode === 'quick') applyPreset(preset)
  else applyCreationMode(mode)
  activeDialogTab.value = 'basic'
  markFormPristine()
}

function startCreateMode(mode: CreationMode) {
  prepareCreateDraft(mode)
  createWizardStep.value = mode === 'quick' ? 'preset' : 'form'
}

function continueFromPreset() {
  prepareCreateDraft('quick', selectedQuickPreset.value)
  createWizardStep.value = 'form'
}

async function goBackInCreateWizard() {
  if (editingId.value !== null) return
  if (createWizardStep.value === 'form') {
    const confirmed = await confirmResetDraft('返回上一步')
    if (!confirmed) return
    const currentMode = creationMode.value
    const currentPreset = selectedQuickPreset.value
    prepareCreateDraft(currentMode, currentPreset)
    createWizardStep.value = currentMode === 'quick' ? 'preset' : 'method'
    return
  }
  prepareCreateDraft('quick', customPreset)
  createWizardStep.value = 'method'
}

async function openCreate() {
  resetForm()
  await Promise.all([loadMetadata(), loadGlobalConfig()])
  prepareCreateDraft('quick', customPreset)
  createWizardStep.value = 'method'
  dialogVisible.value = true
}

async function openEdit(row: SmartProxy) {
  resetForm()
  await Promise.all([loadMetadata(), loadGlobalConfig()])
  editingId.value = row.id
  creationMode.value = row.source_mode === 'manual' ? 'manual' : 'advanced'
  createWizardStep.value = 'form'
  Object.assign(form, {
    name: row.name,
    description: row.description || '',
    proxy_type: row.proxy_type,
    listen_host: row.listen_host,
    port: row.port,
    strategy: row.strategy,
    stability_priority: row.strategy === 'stable',
    scenario: row.scenario,
    data_source: row.data_source || 'subscription',
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
  antNodeIds.value = [...(row.ant_node_ids || [])]
  antStrategyNodeIds.value = [...(row.ant_strategy_node_ids || [])]
  pruneStrategyNodesToManualSource()
  await loadNodeLabelCache([...selectedManualNodeIds.value, ...selectedStrategyNodeIds.value])
  protocolTypes.value = [...row.protocol_types]
  ipWhitelistText.value = (row.ip_whitelist || []).join('\n')
  const { data: config } = await http.get(`/smart-proxies/${row.id}/config`)
  applyTrafficConfigToForm(config)
  markFormPristine()
  dialogVisible.value = true
}

function payload() {
  const mode = form.source_mode
  const antSource = isAntSource.value
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
    country_codes: antSource || mode === 'country' ? countryCodes.value.map((item) => item.trim().toUpperCase()).filter(Boolean) : [],
    tags: antSource || mode === 'tag' ? tags.value.map((item) => item.trim()).filter(Boolean) : [],
    subscription_ids: !antSource && mode === 'subscription' ? subscriptionIds.value : [],
    node_ids: !antSource && mode === 'manual' ? nodeIds.value : [],
    strategy_node_ids: antSource ? [] : strategyNodeIds.value,
    ant_node_ids: antSource && mode === 'manual' ? antNodeIds.value : [],
    ant_strategy_node_ids: antSource ? antStrategyNodeIds.value : [],
    protocol_types: mode === 'manual' ? [] : protocolTypes.value.map((item) => item.trim().toLowerCase()).filter(Boolean),
    ip_whitelist: splitListText(ipWhitelistText.value),
  }
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写代理名称')
    return
  }
  if (proxyNameError.value) {
    ElMessage.warning(proxyNameError.value)
    activeDialogTab.value = 'basic'
    return
  }
  if (form.source_mode === 'manual' && activeManualIds().length === 0) {
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
    if (isAntSource.value) {
      const { data } = await http.get('/ant-proxy/nodes')
      let items = data.items.map((item: any) => ({
        id: String(item.id),
        name: item.name,
        type: item.transport || item.cipher || 'ant',
        server: item.server,
        port: item.port,
        country: item.country || item.city || null,
        country_code: item.country_code || null,
        tags: [`line:${item.line_type}`, item.line_label, `source:${item.source}`].filter(Boolean),
        latency: item.latency_ms,
        source_subscription_id: null,
        source_subscription_name: item.line_label || item.source || '蚂蚁代理',
        source_group: item.source || item.group || '',
        enabled: true,
      })) as NodeItem[]
      const q = nodeQ.value.trim().toLowerCase()
      if (q) {
        items = items.filter((item) =>
          [item.name, item.server, item.source_subscription_name, item.source_group, item.country, item.country_code]
            .join(' ')
            .toLowerCase()
            .includes(q),
        )
      }
      if (nodeCountry.value) {
        items = items.filter((item) => String(item.country_code || '').toUpperCase() === nodeCountry.value.toUpperCase())
      }
      if (nodeGroup.value.trim()) {
        const group = nodeGroup.value.trim().toLowerCase()
        items = items.filter((item) =>
          [item.source_subscription_name, item.source_group, ...(item.tags || [])].join(' ').toLowerCase().includes(group),
        )
      }
      items = items.filter((item) => antNodeMatchesExtraFilters(item))
      items.forEach((item) => {
        nodeCache.value[nodeCacheKey(item.id)] = item
      })
      nodeOptions.value = nodePickerMode.value === 'strategy' ? items.filter((item) => sourceNodeMatches(item)) : items
      return
    }

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
      nodeCache.value[nodeCacheKey(item.id)] = item
    })
    nodeOptions.value = nodePickerMode.value === 'strategy'
      ? items.filter((item: NodeItem) => sourceNodeMatches(item))
      : items
  } finally {
    nodePickerLoading.value = false
  }
}

async function loadNodeLabelCache(nodeIdsToLoad: NodeKey[]) {
  const missingIds = [...new Set(nodeIdsToLoad)].filter((nodeId) => !nodeCache.value[nodeCacheKey(nodeId)])
  if (!missingIds.length) return
  if (isAntSource.value) {
    try {
      const { data } = await http.get('/ant-proxy/nodes')
      data.items.forEach((item: any) => {
        const node: NodeItem = {
          id: String(item.id),
          name: item.name,
          type: item.transport || item.cipher || 'ant',
          server: item.server,
          port: item.port,
          country: item.country || item.city || null,
          country_code: item.country_code || null,
          tags: [`line:${item.line_type}`, item.line_label, `source:${item.source}`].filter(Boolean),
          latency: item.latency_ms,
          source_subscription_id: null,
          source_subscription_name: item.line_label || item.source || '蚂蚁代理',
          source_group: item.source || item.group || '',
          enabled: true,
        }
        nodeCache.value[nodeCacheKey(node.id)] = node
      })
    } catch {
      // Ant 节点尚未加载时保留原始 ID 标签。
    }
    return
  }
  const { data } = await http.get('/nodes')
  const items = data.items.filter((item: NodeItem) => Number.isInteger(item.id))
  items.forEach((item: NodeItem) => {
    nodeCache.value[nodeCacheKey(item.id)] = item
  })
}

function normalizedProtocolTypes() {
  return protocolTypes.value.map((item) => item.trim().toLowerCase()).filter(Boolean)
}

function antNodeMatchesExtraFilters(node: NodeItem) {
  if (!isAntSource.value) return true
  if (countryCodes.value.length) {
    const selectedCountries = countryCodes.value.map((item) => item.trim().toUpperCase()).filter(Boolean)
    if (!selectedCountries.includes(String(node.country_code || '').toUpperCase())) return false
  }
  if (tags.value.length) {
    const selectedTags = new Set(tags.value.map((item) => item.trim()).filter(Boolean))
    if (!(node.tags || []).some((item) => selectedTags.has(String(item).trim()))) return false
  }
  const protocols = normalizedProtocolTypes()
  if (protocols.length && !protocols.includes(String(node.type || '').toLowerCase())) return false
  return true
}

function sourceNodeMatches(node: NodeItem) {
  if (!node.enabled) return false
  if (isAntSource.value) {
    if (!antNodeMatchesExtraFilters(node)) return false
    if (form.source_mode === 'manual') return activeManualIds().map((item) => String(item)).includes(String(node.id))
    return true
  }
  if (form.source_mode !== 'manual') {
    const protocols = normalizedProtocolTypes()
    if (protocols.length && !protocols.includes(String(node.type || '').toLowerCase())) return false
  }
  if (form.source_mode === 'manual') return activeManualIds().map((item) => String(item)).includes(String(node.id))
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
  nodeSelectionDraft.value = mode === 'strategy' ? [...activeStrategyIds()] : [...activeManualIds()]
  nodePickerVisible.value = true
  await loadNodeOptions()
}

function toggleNodeDraft(nodeId: NodeKey, checked: boolean) {
  if (checked && !nodeSelectionDraft.value.includes(nodeId)) {
    nodeSelectionDraft.value.push(nodeId)
  } else if (!checked) {
    nodeSelectionDraft.value = nodeSelectionDraft.value.filter((item) => item !== nodeId)
  }
}

function handleNodeDraftChange(nodeId: NodeKey, checked: boolean | string | number) {
  toggleNodeDraft(nodeId, Boolean(checked))
}

function confirmNodeSelection() {
  if (nodePickerMode.value === 'strategy') {
    setActiveStrategyIds([...nodeSelectionDraft.value])
    nodePickerVisible.value = false
    return
  }
  setActiveManualIds([...nodeSelectionDraft.value])
  form.source_mode = 'manual'
  pruneStrategyNodesToManualSource()
  creationMode.value = 'manual'
  selectedPresetKey.value = ''
  nodePickerVisible.value = false
}

function removeSelectedNode(nodeId: NodeKey) {
  setActiveManualIds(activeManualIds().filter((item) => item !== nodeId))
  nodeSelectionDraft.value = nodeSelectionDraft.value.filter((item) => item !== nodeId)
  setActiveStrategyIds(activeStrategyIds().filter((item) => item !== nodeId))
}

function moveSelectedNode(index: number, direction: -1 | 1) {
  const nextIndex = index + direction
  const current = activeManualIds()
  if (nextIndex < 0 || nextIndex >= current.length) return
  const next = [...current]
  const [item] = next.splice(index, 1)
  next.splice(nextIndex, 0, item)
  setActiveManualIds(next)
  nodeSelectionDraft.value = [...next]
}

function clearSelectedNodes() {
  clearManualNodes()
}

function removeStrategyNode(nodeId: NodeKey) {
  setActiveStrategyIds(activeStrategyIds().filter((item) => item !== nodeId))
  if (nodePickerMode.value === 'strategy') {
    nodeSelectionDraft.value = nodeSelectionDraft.value.filter((item) => item !== nodeId)
  }
}

function moveStrategyNode(index: number, direction: -1 | 1) {
  const nextIndex = index + direction
  const current = activeStrategyIds()
  if (nextIndex < 0 || nextIndex >= current.length) return
  const next = [...current]
  const [item] = next.splice(index, 1)
  next.splice(nextIndex, 0, item)
  setActiveStrategyIds(next)
  if (nodePickerMode.value === 'strategy') nodeSelectionDraft.value = [...next]
}

function nodeLabelById(nodeId: NodeKey) {
  const node = nodeOptions.value.find((item) => item.id === nodeId) || nodeCache.value[nodeCacheKey(nodeId)]
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
  return 'danger'
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
.smart-proxy-toolbar-actions {
  flex: 1 1 auto;
  justify-content: flex-start;
  gap: 8px;
}

.smart-proxy-toolbar-actions :deep(.el-button) {
  min-height: 32px;
  padding-right: 11px;
  padding-left: 11px;
  margin-left: 0;
}

.toolbar-label-short {
  display: none;
}

.proxy-name-cell {
  display: grid;
  min-width: 0;
  justify-items: center;
  gap: 6px;
  text-align: center;
}

.proxy-name-cell strong {
  max-width: 100%;
  overflow: hidden;
  color: var(--heading);
  font-weight: 650;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.proxy-name-cell :deep(.el-tag) {
  flex: 0 0 auto;
}

.current-node-cell {
  display: grid;
  min-width: 0;
  justify-items: center;
  gap: 4px;
  text-align: center;
}

.current-node-cell > span {
  max-width: 100%;
  overflow: hidden;
  color: var(--heading);
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.current-node-cell :deep(.el-button) {
  min-height: auto;
  padding: 0;
  font-size: 12px;
  line-height: 1.35;
}

:global(.smart-proxy-dialog .el-dialog__header) {
  border-bottom: 0;
}

:global(.smart-proxy-dialog .el-dialog__body) {
  padding-top: 4px;
}

:global(.smart-proxy-dialog .el-dialog__footer) {
  border-top: 0;
  padding-top: 12px;
}

:global(.smart-proxy-reset-confirm .el-message-box__header) {
  border-bottom: 0;
}

:global(.smart-proxy-reset-confirm .el-message-box__content) {
  padding-top: 4px;
  padding-bottom: 6px;
}

:global(.smart-proxy-reset-confirm .el-message-box__btns) {
  border-top: 0;
  padding-top: 10px;
}

.create-wizard {
  display: grid;
  gap: 14px;
}

.wizard-stepper {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin: 0;
  padding: 8px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  list-style: none;
}

.wizard-stepper li {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 36px;
  padding: 6px 8px;
  border-radius: 6px;
  color: var(--el-text-color-secondary);
}

.wizard-stepper li.active {
  background: var(--el-bg-color);
  color: var(--accent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 46%, transparent);
}

.wizard-stepper li.done {
  color: var(--el-color-success);
}

.wizard-step-index {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 1px solid currentColor;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

.wizard-stepper li.active .wizard-step-index {
  border-color: var(--accent);
  background: var(--accent);
  color: #fff;
}

.wizard-stepper li.done .wizard-step-index {
  border-color: var(--el-color-success);
  background: var(--el-color-success);
  color: #fff;
}

.wizard-step-text {
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wizard-section {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid color-mix(in srgb, var(--el-border-color) 78%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--el-fill-color-lighter) 62%, var(--el-bg-color));
}

.wizard-section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
}

.wizard-section-head div {
  display: grid;
  gap: 3px;
}

.wizard-section-head em {
  color: var(--el-text-color-secondary);
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.wizard-section-head strong {
  color: var(--el-text-color-primary);
  font-size: 17px;
  line-height: 1.35;
}

.wizard-section-head span {
  max-width: 520px;
  color: var(--el-text-color-secondary);
  line-height: 1.45;
  text-align: right;
}

.wizard-option-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.wizard-option-card {
  display: flex;
  min-width: 0;
  min-height: 124px;
  flex-direction: column;
  align-items: flex-start;
  gap: 9px;
  padding: 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease,
    box-shadow 0.16s ease;
}

.wizard-option-card:hover {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 5%, var(--el-bg-color));
  box-shadow: var(--dashboard-shadow);
}

.wizard-option-head {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.wizard-option-title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.35;
}

.wizard-option-arrow {
  flex: 0 0 auto;
  padding: 2px 8px;
  border: 1px solid color-mix(in srgb, var(--accent) 44%, transparent);
  border-radius: 999px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 650;
}

.wizard-option-desc {
  flex: 1;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.wizard-option-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.wizard-preset-grid {
  margin-bottom: 0;
}

.create-form-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.create-form-summary div {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.create-form-summary strong {
  color: var(--el-text-color-primary);
}

.create-form-summary span {
  min-width: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.summary-back-button {
  flex: 0 0 auto;
  margin-left: 0;
}

.smart-proxy-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.smart-proxy-dialog-footer :deep(.el-button) {
  margin-left: 0;
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
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.preset-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  min-height: 116px;
  padding: 13px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease,
    box-shadow 0.16s ease;
}

.preset-card:hover,
.preset-card.active {
  border-color: var(--accent);
}

.preset-card.active {
  background: color-mix(in srgb, var(--accent) 8%, var(--el-bg-color));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 34%, transparent);
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

.smart-proxy-mobile-card {
  display: grid;
  gap: 12px;
}

.smart-proxy-mobile-card .mobile-card-head,
.smart-proxy-mobile-card .mobile-kv,
.smart-proxy-mobile-card .mobile-card-actions {
  margin-top: 0;
}

.smart-proxy-mobile-card .mobile-card-head {
  align-items: flex-start;
}

.smart-proxy-mobile-card .mobile-card-head > :deep(.el-tag) {
  flex: 0 0 auto;
}

.smart-proxy-mobile-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.smart-proxy-mobile-summary-item {
  display: grid;
  min-width: 0;
  align-content: start;
  gap: 6px;
  border: 1px solid color-mix(in srgb, var(--line) 78%, transparent);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--panel) 58%, var(--panel-soft));
  padding: 9px 10px;
}

.smart-proxy-mobile-summary-item > span,
.smart-proxy-mobile-section-head,
.smart-proxy-mobile-current-copy span {
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.1em;
  line-height: 1;
  text-transform: uppercase;
}

.smart-proxy-mobile-summary-item > strong {
  min-width: 0;
  overflow: hidden;
  color: var(--heading);
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.smart-proxy-mobile-summary-item :deep(.el-tag) {
  justify-self: start;
  max-width: 100%;
}

.smart-proxy-mobile-summary-item :deep(.el-tag__content) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.smart-proxy-mobile-section {
  display: grid;
  min-width: 0;
  gap: 9px;
  border: 1px solid color-mix(in srgb, var(--line) 78%, transparent);
  border-radius: var(--radius);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--panel-soft) 94%, var(--accent) 6%), var(--panel-soft)),
    var(--panel-soft);
  padding: 10px;
}

.smart-proxy-mobile-card .mobile-endpoint-list {
  align-items: stretch;
  gap: 8px;
}

.smart-proxy-mobile-card .mobile-endpoint-list .endpoint-row {
  width: 100%;
  max-width: none;
  grid-template-columns: 74px minmax(0, 1fr) 28px;
}

.smart-proxy-mobile-current {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 12px;
}

.smart-proxy-mobile-current-copy {
  display: grid;
  min-width: 0;
  gap: 6px;
}

.smart-proxy-mobile-current-copy strong {
  min-width: 0;
  overflow: hidden;
  color: var(--heading);
  font-size: 13px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.smart-proxy-mobile-current :deep(.el-button) {
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent-soft) 70%, transparent);
  font-size: 12px;
  line-height: 1.35;
  white-space: nowrap;
}

.smart-proxy-mobile-note {
  border-top: 1px solid color-mix(in srgb, var(--line) 72%, transparent);
  padding-top: 10px;
}

.smart-proxy-mobile-note div {
  grid-template-columns: 48px minmax(0, 1fr);
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

.diagnosis-dialog-content {
  min-width: 0;
}

.diagnosis-mobile-only {
  display: none;
}

.diagnosis-mobile-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}

.diagnosis-kv-card,
.diagnosis-result-card {
  min-width: 0;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.diagnosis-kv-card {
  display: grid;
  align-content: start;
  gap: 6px;
  padding: 10px;
}

.diagnosis-kv-card.is-wide {
  grid-column: 1 / -1;
}

.diagnosis-kv-card span,
.diagnosis-card-kv dt {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
}

.diagnosis-kv-card strong,
.diagnosis-card-kv dd {
  min-width: 0;
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.diagnosis-kv-value {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.diagnosis-kv-value strong {
  flex: 1 1 auto;
}

.diagnosis-kv-value .el-tag {
  flex: 0 0 auto;
}

.diagnosis-mobile-list {
  gap: 10px;
  margin-bottom: 14px;
}

.diagnosis-result-card {
  padding: 12px;
}

.diagnosis-result-head {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.diagnosis-result-head strong {
  min-width: 0;
  color: var(--el-text-color-primary);
  font-size: 14px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.diagnosis-result-head .el-tag {
  flex: 0 0 auto;
}

.diagnosis-card-kv {
  display: grid;
  gap: 8px;
  margin: 12px 0 0;
}

.diagnosis-card-kv div {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.diagnosis-card-kv dt {
  margin: 0;
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

.node-picker-mobile-list {
  display: none;
}

.node-picker-toolbar .el-input,
.node-picker-toolbar .el-select {
  width: 220px;
}

.picker-selected {
  display: grid;
  gap: 8px;
  min-height: 32px;
  margin-top: 10px;
}

.picker-selected-head {
  display: none;
}

.picker-selected-tags {
  margin-top: 0;
}

.picker-selected-empty {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.label-with-help {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
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

@media (max-width: 880px) {
  .smart-proxy-toolbar-actions {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 6px;
  }

  .smart-proxy-toolbar-actions :deep(.el-button) {
    min-height: 36px;
    padding-right: 6px;
    padding-left: 6px;
  }

  .toolbar-label-full {
    display: none;
  }

  .toolbar-label-short {
    display: inline;
  }

  .create-wizard {
    min-height: 0;
    gap: 12px;
  }

  .wizard-stepper {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 5px;
    padding: 6px;
  }

  .wizard-stepper li {
    gap: 6px;
    min-height: 34px;
    padding: 5px 6px;
  }

  .wizard-step-index {
    width: 20px;
    height: 20px;
  }

  .wizard-step-text {
    font-size: 12px;
  }

  .wizard-section {
    padding: 12px;
  }

  .wizard-section-head {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .wizard-section-head span {
    max-width: none;
    text-align: left;
  }

  .wizard-option-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }

  .wizard-option-card {
    min-height: 118px;
    padding: 14px;
  }

  .create-form-summary {
    align-items: stretch;
    flex-direction: column;
  }

  .create-form-summary .summary-back-button {
    align-self: flex-start;
    min-height: 34px;
    padding: 0 12px;
    border-color: color-mix(in srgb, var(--accent) 50%, var(--el-border-color));
    background: color-mix(in srgb, var(--accent) 7%, var(--el-bg-color));
    color: var(--accent);
    font-weight: 650;
  }

  .smart-proxy-dialog-footer {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  .smart-proxy-dialog-footer :deep(.el-button) {
    width: 100%;
    min-width: 0;
  }

  .smart-proxy-dialog-footer :deep(.el-button:last-child:nth-child(odd)) {
    grid-column: 1 / -1;
  }

  .diagnosis-guide {
    grid-template-columns: minmax(0, 1fr);
    align-items: stretch;
    gap: 12px;
    padding: 12px;
  }

  .diagnosis-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    justify-content: stretch;
  }

  .diagnosis-actions :deep(.el-button),
  .diagnosis-log-entry :deep(.el-button) {
    width: 100%;
    min-width: 0;
    min-height: 38px;
    margin-left: 0;
    padding-right: 8px;
    padding-left: 8px;
    white-space: nowrap;
  }

  .diagnosis-actions :deep(.el-button:last-child:nth-child(odd)) {
    grid-column: 1 / -1;
  }

  .diagnosis-actions :deep(.el-button > span),
  .diagnosis-log-entry :deep(.el-button > span) {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .diagnosis-log-entry {
    justify-content: stretch;
  }

  .diagnosis-section-title {
    align-items: center;
    margin-bottom: 8px;
  }

  .diagnosis-desktop-block {
    display: none;
  }

  .diagnosis-mobile-grid.diagnosis-mobile-only {
    display: grid;
  }

  .diagnosis-mobile-list.diagnosis-mobile-only {
    display: grid;
  }

  .node-picker-dialog :deep(.el-dialog__body) {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
  }

  .node-picker-toolbar {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 112px;
    gap: 8px;
    align-items: stretch;
    margin-bottom: 12px;
  }

  .node-picker-toolbar > .el-input:first-child,
  .node-picker-toolbar > .el-select {
    grid-column: 1 / -1;
  }

  .node-picker-toolbar .el-input,
  .node-picker-toolbar .el-select,
  .node-picker-toolbar :deep(.el-button) {
    width: 100%;
    min-width: 0;
    min-height: 38px;
  }

  .node-picker-table {
    display: none;
  }

  .node-picker-mobile-list {
    display: grid;
    flex: 1 1 auto;
    gap: 10px;
    min-height: 260px;
    overflow: auto;
    padding-right: 2px;
    -webkit-overflow-scrolling: touch;
  }

  .node-picker-card {
    min-width: 0;
    border: 1px solid var(--el-border-color);
    border-radius: 8px;
    background: var(--el-fill-color-lighter);
    padding: 12px;
    transition:
      border-color 0.16s ease,
      background-color 0.16s ease;
  }

  .node-picker-card.is-selected {
    border-color: var(--el-color-primary);
    background: color-mix(in srgb, var(--el-color-primary) 9%, var(--el-fill-color-lighter));
  }

  .node-picker-card-head {
    display: grid;
    grid-template-columns: 24px minmax(0, 1fr) auto;
    gap: 8px;
    align-items: start;
  }

  .node-picker-card-title {
    min-width: 0;
  }

  .node-picker-card-title strong,
  .node-picker-card-title span {
    display: block;
    min-width: 0;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .node-picker-card-title strong {
    color: var(--el-text-color-primary);
    font-size: 14px;
    line-height: 1.4;
  }

  .node-picker-card-title span {
    margin-top: 3px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 1.35;
  }

  .node-picker-card-meta {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin: 12px 0 0;
  }

  .node-picker-card-meta div {
    min-width: 0;
  }

  .node-picker-card-meta .is-wide {
    grid-column: 1 / -1;
  }

  .node-picker-card-meta dt,
  .node-picker-card-meta dd {
    margin: 0;
    min-width: 0;
    line-height: 1.4;
  }

  .node-picker-card-meta dt {
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  .node-picker-card-meta dd {
    margin-top: 3px;
    color: var(--el-text-color-primary);
    font-size: 13px;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .picker-selected {
    flex: 0 0 auto;
    margin-top: 12px;
    padding: 10px;
    border: 1px solid var(--el-border-color);
    border-radius: 8px;
    background: var(--el-fill-color-lighter);
  }

  .picker-selected-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  .picker-selected-head strong {
    color: var(--el-color-primary);
    font-size: 13px;
  }

  .picker-selected-tags {
    max-height: 104px;
    margin-top: 8px;
    overflow: auto;
    -webkit-overflow-scrolling: touch;
  }

  .picker-selected-tags .el-tag {
    max-width: 100%;
  }

  .picker-selected-tags .el-tag :deep(.el-tag__content) {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .picker-selected-tags.is-empty {
    min-height: 24px;
    align-items: center;
  }

  .node-picker-dialog :deep(.el-dialog__footer) {
    display: grid;
    grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
    gap: 10px;
  }

  .node-picker-dialog :deep(.el-dialog__footer .el-button) {
    width: 100%;
    margin-left: 0;
  }
}

@media (max-width: 360px) {
  .smart-proxy-toolbar-actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .diagnosis-mobile-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .diagnosis-actions {
    grid-template-columns: minmax(0, 1fr);
  }

  .smart-proxy-dialog-footer {
    grid-template-columns: minmax(0, 1fr);
  }

  .node-picker-toolbar,
  .node-picker-card-meta,
  .node-picker-dialog :deep(.el-dialog__footer) {
    grid-template-columns: minmax(0, 1fr);
  }

  .node-picker-toolbar > .el-input,
  .node-picker-toolbar > .el-select {
    grid-column: 1 / -1;
  }
}
</style>
