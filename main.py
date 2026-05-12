import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from dotenv import load_dotenv
from typing import Optional, Dict, List, Any, Tuple
from enum import Enum

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE & CONSTANTS
# ============================================================================

PC_DATABASE: Dict[str, Any] = {}

# Conversation states
BUDGET = 0
BUILD_TYPE = 1
UPGRADE_MENU = 2
UPGRADE_SELECTION = 3

class BuildType(Enum):
    """Build type enumeration."""
    GAMING = 'gaming'
    CONTENT_CREATION = 'content_creation'

# ============================================================================
# BUILD CONFIGURATION WITH BALANCED ALLOCATION
# ============================================================================

BUILD_CONFIGS = {
    'gaming': {
        'description': '🎮 Gaming Build',
        'budget_allocation': {
            'gpu': 0.45,
            'cpu': 0.16,
            'motherboard': 0.08,
            'ram': 0.10,
            'cooler': 0.04,
            'storage': 0.08,
            'case': 0.03,
            'psu': 0.06
        },
        'gpu_weight': 0.50,
        'cpu_weight': 0.30,
        'performance_emphasis': 'gpu'
    },
    'content_creation': {
        'description': '🎬 Content Creation Build',
        'budget_allocation': {
            'cpu': 0.30,
            'ram': 0.25,
            'gpu': 0.18,
            'motherboard': 0.10,
            'cooler': 0.08,
            'storage': 0.05,
            'case': 0.02,
            'psu': 0.02
        },
        'gpu_weight': 0.25,
        'cpu_weight': 0.60,
        'performance_emphasis': 'cpu'
    }
}

# GPU Tier system for balance checking
class GPUTier(Enum):
    """GPU performance tiers."""
    ENTRY = 1
    MAINSTREAM = 2
    HIGH_END = 3
    FLAGSHIP = 4

GPU_TIER_MAPPING = {
    'RTX 5050': GPUTier.ENTRY,
    'RTX 5060': GPUTier.ENTRY,
    'RTX 5070': GPUTier.MAINSTREAM,
    'RTX 5070 Ti': GPUTier.MAINSTREAM,
    'RTX 5080': GPUTier.HIGH_END,
    'RTX 5090': GPUTier.FLAGSHIP,
}

# CPU Tier system for balance checking
class CPUTier(Enum):
    """CPU performance tiers."""
    ENTRY = 1
    MID_RANGE = 2
    HIGH_END = 3
    FLAGSHIP = 4

CPU_TIER_MAPPING = {
    'Core i5-14400F': CPUTier.ENTRY,
    'Core i5-14600K': CPUTier.ENTRY,
    'Core i5-14600KF': CPUTier.ENTRY,
    'Core i7-14700F': CPUTier.MID_RANGE,
    'Core i7-14700K': CPUTier.MID_RANGE,
    'Core i7-14700KF': CPUTier.MID_RANGE,
    'Core i9-14900F': CPUTier.HIGH_END,
    'Core i9-14900K': CPUTier.HIGH_END,
    'Core i9-14900KF': CPUTier.HIGH_END,
    'Core i9-14900KS': CPUTier.FLAGSHIP,
    'Ryzen 5 7600': CPUTier.ENTRY,
    'Ryzen 5 7600X': CPUTier.ENTRY,
    'Ryzen 5 9600X': CPUTier.ENTRY,
    'Ryzen 7 7700': CPUTier.MID_RANGE,
    'Ryzen 7 7700X': CPUTier.MID_RANGE,
    'Ryzen 7 9700X': CPUTier.MID_RANGE,
    'Ryzen 9 7900X': CPUTier.HIGH_END,
    'Ryzen 9 9900X': CPUTier.HIGH_END,
    'Ryzen 9 7950X': CPUTier.FLAGSHIP,
    'Ryzen 9 9950X': CPUTier.FLAGSHIP,
}

# Motherboard tier mapping
MOTHERBOARD_TIER_MAPPING = {
    'H610': 1,
    'H770': 2,
    'Z790': 3,
    'B850': 2,
    'X870': 3,
    'X870-E': 4,
}

# ============================================================================
# BALANCE RULES ENGINE
# ============================================================================

class BalanceValidator:
    """Validates and enforces build balance."""

    @staticmethod
    def get_gpu_tier(gpu: Dict) -> GPUTier:
        """Get GPU tier from model name."""
        for tier_gpu, tier in GPU_TIER_MAPPING.items():
            if tier_gpu in gpu['model']:
                return tier
        return GPUTier.ENTRY

    @staticmethod
    def get_cpu_tier(cpu: Dict) -> CPUTier:
        """Get CPU tier from model name."""
        for tier_cpu, tier in CPU_TIER_MAPPING.items():
            if tier_cpu in cpu['model']:
                return tier
        return CPUTier.MID_RANGE

    @staticmethod
    def get_motherboard_tier(motherboard: Dict) -> int:
        """Get motherboard tier from chipset."""
        chipset = motherboard.get('chipset', '')
        for chip, tier in MOTHERBOARD_TIER_MAPPING.items():
            if chip in chipset:
                return tier
        return 2

    @staticmethod
    def is_balanced(cpu: Dict, gpu: Dict, motherboard: Dict, build_type: str) -> Tuple[bool, str]:
        """Check if build is balanced."""
        cpu_tier = BalanceValidator.get_cpu_tier(cpu)
        gpu_tier = BalanceValidator.get_gpu_tier(gpu)
        mobo_tier = BalanceValidator.get_motherboard_tier(motherboard)

        if build_type == 'gaming':
            if gpu_tier.value < cpu_tier.value - 1:
                return False, f"GPU tier ({gpu_tier.name}) is too low for CPU tier ({cpu_tier.name})"

        if build_type == 'content_creation':
            if cpu_tier.value < gpu_tier.value - 1:
                return False, f"CPU tier ({cpu_tier.name}) is too low for GPU tier ({gpu_tier.name})"

        if build_type == 'gaming':
            if mobo_tier > cpu_tier.value + 1:
                return False, f"Motherboard is overkill for CPU tier ({cpu_tier.name})"

        return True, "Build is balanced"

    @staticmethod
    def get_min_gpu_tier_for_budget(budget: int, build_type: str) -> GPUTier:
        """Determine minimum GPU tier required for budget."""
        if budget < 1000:
            return GPUTier.ENTRY
        elif budget < 2000:
            return GPUTier.MAINSTREAM
        elif budget < 3500:
            return GPUTier.HIGH_END
        else:
            return GPUTier.FLAGSHIP if build_type == 'gaming' else GPUTier.HIGH_END

    @staticmethod
    def get_expected_gpu_tier_for_cpu(cpu: Dict, build_type: str) -> GPUTier:
        """Get expected GPU tier that matches CPU tier for a build type."""
        cpu_tier = BalanceValidator.get_cpu_tier(cpu)
        
        if build_type == 'gaming':
            # For gaming, GPU should match or exceed CPU tier
            if cpu_tier == CPUTier.ENTRY:
                return GPUTier.MAINSTREAM
            elif cpu_tier == CPUTier.MID_RANGE:
                return GPUTier.HIGH_END
            elif cpu_tier == CPUTier.HIGH_END:
                return GPUTier.HIGH_END
            else:  # FLAGSHIP
                return GPUTier.FLAGSHIP
        else:
            # For content creation, GPU can be one tier lower than CPU
            if cpu_tier == CPUTier.ENTRY:
                return GPUTier.ENTRY
            elif cpu_tier == CPUTier.MID_RANGE:
                return GPUTier.MAINSTREAM
            elif cpu_tier == CPUTier.HIGH_END:
                return GPUTier.HIGH_END
            else:
                return GPUTier.HIGH_END

# ============================================================================
# PERFORMANCE SCORING ENGINE
# ============================================================================

class PerformanceScorer:
    """Scores components based on performance and build type."""

    @staticmethod
    def score_gpu(gpu: Dict, config: Dict) -> float:
        """Score GPU performance."""
        score = 0.0
        
        score += gpu.get('memory_gb', 8) * 3
        
        pcie_gen = gpu.get('pcie_gen', 3)
        score += (pcie_gen - 3) * 15
        
        if 'GDDR7' in gpu.get('memory_type', ''):
            score += 20
        elif 'GDDR6' in gpu.get('memory_type', ''):
            score += 10
        
        tier = BalanceValidator.get_gpu_tier(gpu)
        score += tier.value * 50
        
        return score * config.get('gpu_weight', 0.5)

    @staticmethod
    def score_cpu(cpu: Dict, config: Dict) -> float:
        """Score CPU performance."""
        score = 0.0
        
        score += cpu.get('cores', 8) * 5
        score += cpu.get('threads', 16) * 2
        score += cpu.get('boost_ghz', 4.0) * 15
        
        tier = BalanceValidator.get_cpu_tier(cpu)
        score += tier.value * 40
        
        return score * config.get('cpu_weight', 0.3)

    @staticmethod
    def score_motherboard(motherboard: Dict) -> float:
        """Score motherboard features."""
        score = 0.0
        
        score += motherboard.get('m2_slots', 3) * 10
        score += (motherboard.get('max_memory_speed', 3200) - 3200) * 0.05
        
        tier = BalanceValidator.get_motherboard_tier(motherboard)
        score += tier * 20
        
        return score

    @staticmethod
    def score_ram(ram: Dict, motherboard_max_speed: Optional[int] = None) -> float:
        """Score RAM performance, prioritising speeds close to the motherboard's maximum.

        Scoring breakdown (approximate relative weights):
          - Speed proximity  ~50 %  — normalised 0-1 ratio of effective_speed / max_speed,
                                      scaled to 100 pts.  Rewards kits whose speed is as
                                      close as possible to what the board can actually run.
                                      RAM faster than the board cap is capped at 1.0 (no
                                      penalty, but no bonus either).
          - Capacity         ~35 %  — log₂ scaling so doubling capacity adds a fixed bonus
                                      rather than letting raw GB linearly swamp speed.
          - CAS latency      ~15 %  — lower latency is better; bounded so extreme CAS values
                                      can't flip the speed ranking.
        """
        ram_speed = ram.get('speed_mhz', 3200)
        capacity  = ram.get('capacity_gb', 16)
        cas       = ram.get('cas_latency', 16)

        # --- Speed proximity score (0–100) -----------------------------------
        if motherboard_max_speed and motherboard_max_speed > 0:
            # Clamp: RAM faster than the board cap runs at cap; no overclock bonus.
            effective_speed = min(ram_speed, motherboard_max_speed)
            speed_score = (effective_speed / motherboard_max_speed) * 100
        else:
            # No board cap known — reward absolute speed on a reasonable DDR5 scale.
            speed_score = min(ram_speed / 8000, 1.0) * 100

        # --- Capacity score (0–~35) ------------------------------------------
        # log2(16 GB) = 4 → 0 pts baseline; log2(128 GB) = 7 → +21 pts.
        # Using 4 as the zero-point so 16 GB = 0, 32 GB ≈ 7, 64 GB ≈ 14, 128 GB ≈ 21.
        import math
        capacity_score = max(0.0, math.log2(max(capacity, 1)) - 4) * 7

        # --- CAS latency score (0–15) ----------------------------------------
        # Treat CAS 16 as baseline (DDR4) / CAS 30 as baseline (DDR5).
        # Reward lower latency but cap the contribution so it can't override speed.
        cas_baseline = 30 if (motherboard_max_speed or 0) >= 4800 else 16
        cas_score = max(0.0, min((cas_baseline - cas) * 1.5 + 15, 15))

        return speed_score + capacity_score + cas_score

    @staticmethod
    def calculate_overall_score(build: Dict, config: Dict) -> float:
        """Calculate overall build performance score."""
        if not build.get('gpu') or not build.get('cpu'):
            return 0.0

        score = 0.0
        score += PerformanceScorer.score_gpu(build['gpu'], config)
        score += PerformanceScorer.score_cpu(build['cpu'], config)
        score += PerformanceScorer.score_motherboard(build['motherboard']) * 0.2
        
        # Pass motherboard max speed to RAM scorer
        mobo_max_speed = build['motherboard'].get('max_memory_speed')
        score += PerformanceScorer.score_ram(build['ram'], mobo_max_speed) * 0.15
        
        return score

# ============================================================================
# DATABASE LOADER
# ============================================================================

def load_database() -> bool:
    """Load PC parts database."""
    try:
        with open('pc-part-db.json', 'r') as f:
            global PC_DATABASE
            PC_DATABASE = json.load(f)
        logger.info("✅ PC Database loaded successfully")
        return True
    except FileNotFoundError:
        logger.error("❌ pc-part-db.json not found!")
        return False
    except json.JSONDecodeError:
        logger.error("❌ pc-part-db.json is not valid JSON!")
        return False

# ============================================================================
# COMPONENT SELECTION ENGINE
# ============================================================================

class ComponentSelector:
    """Handles intelligent component selection with cost optimization & balance enforcement."""

    @staticmethod
    def _get_components_by_type(component_type: str, param: Any = None) -> List[Dict]:
        """Get available components by type with optional filtering."""
        try:
            if component_type == 'cpu':
                if param == 'gaming':
                    return PC_DATABASE['categories']['intel_14th_gen_cpus']
                elif param == 'content_creation':
                    return PC_DATABASE['categories']['amd_ryzen_8000_cpus']
            
            elif component_type == 'motherboard':
                if param == 'LGA1700':
                    return PC_DATABASE['categories']['intel_motherboards']
                elif param == 'AM5':
                    return PC_DATABASE['categories']['amd_motherboards']
            
            elif component_type == 'ram':
                all_ram = PC_DATABASE['categories']['memory_ram']
                return [r for r in all_ram if r['type'] == param]
            
            elif component_type == 'cooler':
                all_coolers = PC_DATABASE['categories']['cpu_coolers']
                socket, tdp = param['socket'], param['tdp']
                candidates = [c for c in all_coolers if socket in c['socket']]
                return sorted(candidates, key=lambda x: x['price_usd'])
            
            elif component_type == 'gpu':
                return PC_DATABASE['categories']['nvidia_rtx_5000_gpus']
            
            elif component_type == 'storage':
                return PC_DATABASE['categories']['storage_drives']
            
            elif component_type == 'case':
                all_cases = PC_DATABASE['categories']['pc_cases']
                form_factor = param.get('motherboard_form_factor')
                candidates = [c for c in all_cases if form_factor in c['motherboard_support']]
                return candidates if candidates else all_cases
            
            elif component_type == 'psu':
                all_psus = PC_DATABASE['categories']['power_supply_units']
                required_wattage = param
                min_wattage = int(required_wattage * 0.8)
                candidates = [p for p in all_psus if p['wattage'] >= min_wattage]
                return sorted(candidates, key=lambda x: x['price_usd'])
            
            return []
        except Exception as e:
            logger.error(f"Error getting components for {component_type}: {str(e)}")
            return []

    @staticmethod
    def score_price_efficiency(component: Dict, component_type: str, motherboard_max_speed: Optional[int] = None) -> float:
        """Score price efficiency (performance per dollar)."""
        price = component.get('price_usd', 1)
        
        if component_type == 'gpu':
            vram_score = component.get('memory_gb', 8)
            pcie_score = component.get('pcie_gen', 3) * 0.5
            gddr_bonus = 1.5 if 'GDDR7' in component.get('memory_type', '') else 1.0
            total_performance = (vram_score + pcie_score) * gddr_bonus
            return total_performance / price
        
        elif component_type == 'cpu':
            cores_score = component.get('cores', 8)
            boost_score = component.get('boost_ghz', 4.0) * 0.5
            total_performance = cores_score + boost_score
            return total_performance / price
        
        elif component_type == 'ram':
            # Delegate to score_ram so both paths use identical proximity-aware logic.
            # Divide by price to keep this a price-efficiency metric.
            price = max(component.get('price_usd', 1), 1)
            return PerformanceScorer.score_ram(component, motherboard_max_speed) / price
        
        elif component_type == 'storage':
            capacity = component.get('capacity_gb', 512)
            speed = component.get('seq_read_mbs', 5000) / 1000
            total_performance = capacity + speed
            return total_performance / price
        
        elif component_type == 'motherboard':
            m2_slots = component.get('m2_slots', 3)
            max_speed = component.get('max_memory_speed', 3200)
            total_performance = m2_slots + (max_speed / 1000)
            return total_performance / price
        
        elif component_type == 'cooler':
            tdp = component.get('tdp_rating', 150)
            return tdp / price
        
        elif component_type == 'psu':
            wattage = component.get('wattage', 650)
            efficiency_bonus = 1.2 if '80+ Platinum' in component.get('efficiency_rating', '') else \
                              1.1 if '80+ Gold' in component.get('efficiency_rating', '') else 1.0
            total_performance = wattage * efficiency_bonus
            return total_performance / price
        
        elif component_type == 'case':
            gpu_length = component.get('max_gpu_length_mm', 350)
            return gpu_length / price
        
        return 1.0 / price

    @staticmethod
    def select_component(
        component_type: str,
        param: Any,
        max_price: int,
        available_budget: int,
        performance_score_fn: Optional[callable] = None,
        motherboard_max_speed: Optional[int] = None,
        prefer_higher: bool = True
    ) -> Optional[Dict]:
        """Select best component within strict budget constraints."""
        components = ComponentSelector._get_components_by_type(component_type, param)
        
        if not components:
            logger.warning(f"No components found for {component_type}")
            return None
        
        strict_budget = min(max_price, available_budget)
        affordable = [c for c in components if c['price_usd'] <= strict_budget]
        
        if not affordable:
            logger.warning(f"No affordable {component_type} found within ${strict_budget}. Relaxing constraints...")
            affordable = sorted(components, key=lambda x: x['price_usd'])[:5]
            if not affordable:
                return None
        
        logger.info(f"Found {len(affordable)} affordable {component_type}s within ${strict_budget}")
        
        if performance_score_fn:
            # performance_score_fn already closes over motherboard_max_speed via the lambda
            # at the call site — always invoke with just the component argument
            affordable_with_scores = [
                (c, performance_score_fn(c))
                for c in affordable
            ]
            affordable_with_scores.sort(key=lambda x: (-x[1], x[0]['price_usd']))
            selected = affordable_with_scores[0][0]
            logger.debug(f"Selected {component_type} via custom scoring: {selected.get('model')} (${selected['price_usd']})")
        
        else:
            scored_components = [
                (c, ComponentSelector.score_price_efficiency(c, component_type, motherboard_max_speed))
                for c in affordable
            ]
            
            scored_components.sort(key=lambda x: (-x[1], x[0]['price_usd']))
            
            selected = scored_components[0][0]
            efficiency = scored_components[0][1]
            
            logger.debug(
                f"Selected {component_type}: {selected.get('model')} "
                f"(${selected['price_usd']}, efficiency: {efficiency:.3f})"
            )
        
        return selected

# ============================================================================
# BUILD GENERATOR
# ============================================================================

class BuildGenerator:
    """Generates PC builds with strict balance enforcement."""

    @staticmethod
    def generate(
        budget: int,
        build_type: str,
        allocations: Dict[str, float]
    ) -> Dict[str, Any]:
        """Generate a balanced PC build within budget."""
        build = {
            'cpu': None,
            'motherboard': None,
            'ram': None,
            'cooler': None,
            'gpu': None,
            'storage_primary': None,
            'case': None,
            'psu': None,
            'total_cost': 0,
            'remaining_budget': budget,
            'budget_allocation': allocations,
            'total_power_consumption': 0,
            'error_message': None,
            'balance_warnings': [],
            'performance_score': 0.0
        }
        
        spent = 0
        selector = ComponentSelector()
        config = BUILD_CONFIGS[build_type]
        
        try:
            logger.info(f"Starting balanced build: budget=${budget}, type={build_type}")
            
            # ===== STEP 1: SELECT CPU FIRST (REVERSED ORDER FOR BALANCE) =====
            cpu_max = int(budget * allocations['cpu'] * 1.3)
            
            all_cpus = ComponentSelector._get_components_by_type('cpu', build_type)
            
            # Filter CPUs that fit budget
            affordable_cpus = [c for c in all_cpus if c['price_usd'] <= cpu_max]
            if not affordable_cpus:
                build['error_message'] = "No CPU found within budget constraints."
                return build
            
            # Sort by tier (highest first), then by performance (cores, boost), then by price
            affordable_cpus.sort(key=lambda x: (
                -BalanceValidator.get_cpu_tier(x).value,
                -x['cores'],
                -x['boost_ghz'],
                x['price_usd']
            ))
            
            cpu = affordable_cpus[0]
            build['cpu'] = cpu
            spent += cpu['price_usd']
            cpu_tier = BalanceValidator.get_cpu_tier(cpu)
            logger.info(f"CPU: {cpu['model']} (Tier: {cpu_tier.name}, ${cpu['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 2: SELECT MOTHERBOARD =====
            mobo_max = int(budget * allocations['motherboard'] * 1.5)
            all_mobos = ComponentSelector._get_components_by_type('motherboard', cpu['socket'])
            
            balanced_mobos = []
            for mobo in all_mobos:
                mobo_tier = BalanceValidator.get_motherboard_tier(mobo)
                if mobo_tier <= cpu_tier.value + 1 and mobo['price_usd'] <= mobo_max:
                    balanced_mobos.append(mobo)
            
            if balanced_mobos:
                balanced_mobos.sort(key=lambda x: (
                    -BalanceValidator.get_motherboard_tier(x),
                    -x['m2_slots'],
                    x['price_usd']
                ))
                mobo = balanced_mobos[0]
            else:
                mobo = selector.select_component('motherboard', cpu['socket'], mobo_max, budget - spent)
            
            if not mobo:
                build['error_message'] = "No compatible motherboard found."
                return build
            
            build['motherboard'] = mobo
            spent += mobo['price_usd']
            mobo_tier = BalanceValidator.get_motherboard_tier(mobo)
            logger.info(f"Motherboard: {mobo['model']} (Tier: {mobo_tier}, ${mobo['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 3: SELECT GPU BALANCED WITH CPU =====
            # Determine expected GPU tier based on CPU tier
            expected_gpu_tier = BalanceValidator.get_expected_gpu_tier_for_cpu(cpu, build_type)
            
            gpu_max = int(budget * allocations['gpu'] * 1.3)
            all_gpus = ComponentSelector._get_components_by_type('gpu', None)
            
            # Filter GPUs: must be within budget and match expected tier
            balanced_gpus = []
            for g in all_gpus:
                gpu_tier = BalanceValidator.get_gpu_tier(g)
                # Allow tier matching or one tier difference for balance
                if (abs(gpu_tier.value - expected_gpu_tier.value) <= 1 and 
                    g['price_usd'] <= gpu_max and 
                    g['price_usd'] <= budget - spent - 300):  # Leave budget for other components
                    balanced_gpus.append(g)
            
            if balanced_gpus:
                # Sort by tier (prefer matching tier), then by price efficiency
                balanced_gpus.sort(key=lambda x: (
                    abs(BalanceValidator.get_gpu_tier(x).value - expected_gpu_tier.value),
                    -x['memory_gb'],
                    x['price_usd']
                ))
                gpu = balanced_gpus[0]
                logger.info(f"Found {len(balanced_gpus)} balanced GPU options, selecting top match")
            else:
                # Fallback: select best affordable GPU
                logger.warning(f"No balanced GPU found for tier {expected_gpu_tier.name}, selecting best affordable option")
                affordable_gpus = [g for g in all_gpus if g['price_usd'] <= gpu_max and g['price_usd'] <= budget - spent - 300]
                if not affordable_gpus:
                    build['error_message'] = "No GPU found within budget constraints."
                    return build
                affordable_gpus.sort(key=lambda x: x['price_usd'], reverse=True)
                gpu = affordable_gpus[0]
            
            build['gpu'] = gpu
            spent += gpu['price_usd']
            gpu_tier = BalanceValidator.get_gpu_tier(gpu)
            logger.info(f"GPU: {gpu['model']} (Tier: {gpu_tier.name}, Expected: {expected_gpu_tier.name}, ${gpu['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 4: SELECT RAM =====
            ram_max = int(budget * allocations['ram'] * 1.3)
            
            # Get motherboard's max memory speed for RAM compatibility
            motherboard_max_speed = mobo.get('max_memory_speed')
            logger.info(f"Motherboard max memory speed: {motherboard_max_speed} MHz")
            
            ram = selector.select_component(
                'ram',
                mobo['memory_type'],
                ram_max,
                budget - spent,
                performance_score_fn=lambda r, max_speed=motherboard_max_speed: PerformanceScorer.score_ram(r, max_speed),
                motherboard_max_speed=motherboard_max_speed
            )
            if not ram:
                build['error_message'] = "No compatible RAM found."
                return build
            
            build['ram'] = ram
            spent += ram['price_usd']
            logger.info(f"RAM: {ram['model']} (${ram['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 5: SELECT COOLER =====
            cooler_max = int(budget * allocations['cooler'] * 2.0)
            cooler = selector.select_component(
                'cooler',
                {'socket': cpu['socket'], 'tdp': cpu['tdp']},
                cooler_max,
                budget - spent
            )
            if not cooler:
                build['error_message'] = "No compatible CPU cooler found."
                return build
            
            build['cooler'] = cooler
            spent += cooler['price_usd']
            logger.info(f"Cooler: {cooler['model']} (${cooler['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 6: SELECT STORAGE =====
            storage_max = int(budget * allocations['storage'] * 1.3)

            # High-end builds (budget >= $2000) and content creation builds require
            # at least 1 TB storage — pre-filter the pool before selection.
            is_high_end_or_content = (build_type == 'content_creation' or budget >= 2000)
            min_storage_gb = 1000 if is_high_end_or_content else 0
            if min_storage_gb:
                logger.info(
                    f"Applying minimum storage capacity filter: {min_storage_gb} GB "
                    f"(build_type={build_type}, budget=${budget})"
                )

            # Temporarily monkey-patch the storage pool inside _get_components_by_type
            # by filtering directly here so we can pass a constrained list.
            all_drives = PC_DATABASE['categories']['storage_drives']
            eligible_drives = [d for d in all_drives if d.get('capacity_gb', 0) >= min_storage_gb]
            if not eligible_drives:
                # Fallback: relax the cap and pick largest available
                logger.warning("No drives meet minimum capacity — relaxing storage filter.")
                eligible_drives = all_drives

            # Temporarily replace the DB list so select_component picks from filtered pool
            PC_DATABASE['categories']['storage_drives'] = eligible_drives
            storage = selector.select_component(
                'storage',
                None,
                storage_max,
                budget - spent - 200
            )
            PC_DATABASE['categories']['storage_drives'] = all_drives  # restore original list
            if not storage:
                build['error_message'] = "No storage drive found."
                return build
            
            build['storage_primary'] = storage
            spent += storage['price_usd']
            logger.info(f"Storage: {storage['model']} (${storage['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 7: SELECT CASE =====
            case_max = int(budget * allocations['case'] * 2.0)
            case = selector.select_component(
                'case',
                {'motherboard_form_factor': mobo['form_factor']},
                case_max,
                budget - spent - 100
            )
            if not case:
                build['error_message'] = "No suitable case found."
                return build
            
            build['case'] = case
            spent += case['price_usd']
            logger.info(f"Case: {case['model']} (${case['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 8: SELECT PSU =====
            total_tdp = cpu['tdp'] + gpu['tdp']
            required_wattage = int(total_tdp * 1.3) + 100
            
            psu_max = budget - spent
            psu = selector.select_component('psu', required_wattage, psu_max, psu_max)
            
            if not psu:
                estimated_cost = min(psu_max, max(80, int(required_wattage * 0.12)))
                psu = {
                    'id': 'psu_estimated',
                    'brand': 'Generic',
                    'model': f'{required_wattage}W 80+ Bronze',
                    'wattage': required_wattage,
                    'efficiency_rating': '80+ Bronze',
                    'modular_type': 'Fully Modular',
                    'price_usd': estimated_cost
                }
            
            build['psu'] = psu
            spent += psu['price_usd']
            logger.info(f"PSU: {psu['model']} (${psu['price_usd']}) - Spent: ${spent}")
            
            # ===== FINAL BALANCE CHECK =====
            build['total_power_consumption'] = total_tdp
            build['total_cost'] = spent
            build['remaining_budget'] = max(0, budget - spent)
            build['performance_score'] = PerformanceScorer.calculate_overall_score(build, config)
            
            is_balanced, reason = BalanceValidator.is_balanced(cpu, gpu, mobo, build_type)
            if not is_balanced:
                build['balance_warnings'].append(f"⚠️ {reason}")
                logger.warning(f"Balance warning: {reason}")
            
            logger.info(f"✅ Balanced build complete: ${spent}/${budget} (Score: {build['performance_score']:.1f})")
            return build
            
        except Exception as e:
            logger.error(f"Build generation error: {str(e)}")
            build['error_message'] = f"An error occurred: {str(e)}"
            return build

# ============================================================================
# UPGRADE OPTIONS ENGINE
# ============================================================================

class UpgradeEngine:
    """
    Generates and applies balanced upgrade options for individual PC components.

    Design principles
    -----------------
    1. Budget allocation awareness — each component's upgrade ceiling is derived
       from its build-type allocation ratio rather than whatever dollar amount
       happens to be left over after selecting every other part.  This prevents
       e.g. a $20 storage from leaving an apparent $800 'remaining' that the user
       could 'spend' on a GPU upgrade, only to produce a badly unbalanced build.

    2. Performance-per-dollar ranking — candidates are ranked by the marginal
       performance gain they produce divided by their price delta against the
       current component.  The option that gives the best return on each
       upgrade dollar floats to the top rather than the most expensive option
       that still fits.

    3. Build-type balance enforcement — GPU/CPU tier mismatches relative to the
       rest of the build are detected and filtered or warned on before presenting
       options to the user.

    4. Hard compatibility gates — socket, DDR generation, motherboard RAM speed
       cap, cooler TDP, and PSU headroom are enforced as binary pass/fail checks
       before a candidate enters the scoring stage.
    """

    # How much above the nominal allocation ratio an upgrade is allowed to reach.
    # 1.6 means a component allocated 45% of budget may be upgraded up to 72%.
    _UPGRADE_CEILING_MULTIPLIER = 1.6

    # Minimum price improvement over current component to qualify as an upgrade.
    _MIN_PRICE_DELTA = 10  # USD

    @staticmethod
    def _component_budget_ceiling(component_type: str, build_type: str, budget: int) -> int:
        """
        Return the maximum dollar amount that should be spent on a single
        component upgrade, derived from the build-type allocation ratios.

        The ceiling is allocation_ratio * budget * ceiling_multiplier, rounded
        to the nearest dollar.  This keeps upgrade suggestions proportional to
        the build's design intent rather than being driven purely by whatever
        money is left in the pool.
        """
        # Map storage_primary back to 'storage' key used in BUILD_CONFIGS
        config_key = 'storage' if component_type == 'storage_primary' else component_type
        alloc = BUILD_CONFIGS[build_type]['budget_allocation'].get(config_key, 0.08)
        ceiling = int(budget * alloc * UpgradeEngine._UPGRADE_CEILING_MULTIPLIER)
        logger.info(
            f"Budget ceiling for {component_type} ({build_type}): "
            f"${ceiling} (alloc={alloc:.0%}, budget=${budget})"
        )
        return ceiling

    @staticmethod
    def _score_candidate(
        candidate: Dict,
        component_type: str,
        current_build: Dict,
        build_type: str,
    ) -> float:
        """
        Score a candidate component by the marginal performance it adds per
        dollar above the current component's price.

        Returns a value in (0, ∞).  Higher is better.  Returns 0.0 if the
        candidate produces no improvement or is cheaper than the current part.
        """
        current = current_build[component_type]
        price_delta = candidate['price_usd'] - current['price_usd']
        if price_delta < UpgradeEngine._MIN_PRICE_DELTA:
            return 0.0

        config = BUILD_CONFIGS[build_type]

        # Build a temporary build dict with the candidate swapped in so we can
        # call the existing PerformanceScorer without duplicating its logic.
        import copy
        temp_build = copy.copy(current_build)
        temp_build[component_type] = candidate

        new_score = PerformanceScorer.calculate_overall_score(temp_build, config)
        old_score = PerformanceScorer.calculate_overall_score(current_build, config)

        gain = new_score - old_score
        if gain <= 0:
            return 0.0

        return gain / price_delta  # performance gain per dollar

    @staticmethod
    def _passes_compatibility(
        candidate: Dict,
        component_type: str,
        current_build: Dict,
    ) -> Tuple[bool, str]:
        """
        Hard compatibility gate.  Returns (True, '') if the candidate is
        compatible with the rest of the build, or (False, reason) if not.
        """
        mobo = current_build.get('motherboard', {})
        cpu  = current_build.get('cpu', {})

        if component_type == 'cpu':
            required_socket = mobo.get('socket', '')
            if candidate.get('socket') != required_socket:
                return False, f"Socket mismatch: needs {required_socket}, got {candidate.get('socket')}"

        elif component_type == 'ram':
            # DDR generation must match motherboard
            required_type = mobo.get('memory_type', '')
            if candidate.get('type') != required_type:
                return False, f"RAM type mismatch: board needs {required_type}"

        elif component_type == 'cooler':
            cpu_socket = cpu.get('socket', '')
            if cpu_socket not in candidate.get('socket', ''):
                return False, f"Cooler does not support socket {cpu_socket}"
            cpu_tdp = cpu.get('tdp', 0)
            if candidate.get('tdp_rating', 0) < cpu_tdp:
                return False, (
                    f"Cooler TDP rating {candidate.get('tdp_rating')}W "
                    f"is insufficient for CPU TDP {cpu_tdp}W"
                )

        elif component_type == 'psu':
            required_w = current_build.get('total_power_consumption', 0)
            # PSU must cover system TDP with at least 20% headroom
            if candidate.get('wattage', 0) < required_w * 1.20:
                return False, (
                    f"PSU {candidate.get('wattage')}W provides insufficient headroom "
                    f"for {required_w}W system draw"
                )

        return True, ''

    @staticmethod
    def _check_balance_warning(
        candidate: Dict,
        component_type: str,
        current_build: Dict,
        build_type: str,
    ) -> Optional[str]:
        """
        Return a human-readable balance warning if the upgrade would create a
        significant tier mismatch, or None if the build remains well-balanced.
        """
        if component_type == 'gpu':
            cpu_tier  = BalanceValidator.get_cpu_tier(current_build['cpu']).value
            new_gpu_tier = BalanceValidator.get_gpu_tier(candidate).value
            if new_gpu_tier - cpu_tier >= 2:
                return (
                    f"⚠️ GPU tier ({BalanceValidator.get_gpu_tier(candidate).name}) "
                    f"will be significantly ahead of your CPU tier "
                    f"({BalanceValidator.get_cpu_tier(current_build['cpu']).name}). "
                    f"Consider a CPU upgrade too."
                )

        elif component_type == 'cpu':
            gpu_tier  = BalanceValidator.get_gpu_tier(current_build['gpu']).value
            new_cpu_tier = BalanceValidator.get_cpu_tier(candidate).value
            if gpu_tier - new_cpu_tier >= 2:
                return (
                    f"⚠️ Your GPU tier ({BalanceValidator.get_gpu_tier(current_build['gpu']).name}) "
                    f"is significantly ahead of the new CPU tier "
                    f"({BalanceValidator.get_cpu_tier(candidate).name}). "
                    f"This upgrade may not improve gaming performance much."
                )

        return None

    @staticmethod
    def get_compatible_upgrades(
        current_build: Dict,
        component_type: str,
        budget: int,
    ) -> Optional[List[Dict]]:
        """
        Return up to three upgrade candidates for *component_type*, ranked by
        performance gain per upgrade dollar, subject to:

          • Hard compatibility gates (socket, DDR type, TDP, PSU headroom)
          • A per-component budget ceiling derived from the build-type's
            allocation ratios — not just whatever money is left over
          • A minimum price delta so only genuine upgrades are surfaced
          • Build-balance awareness (tier mismatch warnings attached to each
            candidate as 'balance_warning' so callers can display them)
        """
        current_component = current_build.get(component_type)
        if not current_component:
            logger.warning(f"No current component found for {component_type}")
            return None

        build_type  = current_build.get('build_type', 'gaming')
        current_price = current_component['price_usd']

        # --- Budget ceiling --------------------------------------------------
        # The maximum this component should cost in this build, regardless of
        # how cheap the other parts ended up being.
        allocation_ceiling = UpgradeEngine._component_budget_ceiling(
            component_type, build_type, budget
        )
        # Also respect the hard total-build budget: the rest of the build
        # (everything except this component) is fixed, so the most we can spend
        # on this slot is budget minus cost of all other parts.
        other_parts_cost = current_build['total_cost'] - current_price
        hard_ceiling = budget - other_parts_cost
        # Take the stricter of the two ceilings.
        effective_ceiling = min(allocation_ceiling, hard_ceiling)

        logger.info(
            f"Upgrade ceiling for {component_type}: "
            f"allocation=${allocation_ceiling}, hard=${hard_ceiling} → effective=${effective_ceiling}"
        )

        if effective_ceiling <= current_price + UpgradeEngine._MIN_PRICE_DELTA:
            logger.warning(
                f"No budget headroom for {component_type} upgrade "
                f"(ceiling=${effective_ceiling}, current=${current_price})"
            )
            return None

        selector = ComponentSelector()

        # --- Fetch candidate pool --------------------------------------------
        if component_type == 'gpu':
            all_options = selector._get_components_by_type('gpu', None)
        elif component_type == 'cpu':
            all_options = selector._get_components_by_type('cpu', build_type)
        elif component_type == 'ram':
            all_options = selector._get_components_by_type(
                'ram', current_build['motherboard']['memory_type']
            )
        elif component_type == 'cooler':
            all_options = selector._get_components_by_type(
                'cooler',
                {'socket': current_build['cpu']['socket'], 'tdp': current_build['cpu']['tdp']}
            )
        elif component_type == 'storage_primary':
            all_options = selector._get_components_by_type('storage', None)
        elif component_type == 'psu':
            all_options = selector._get_components_by_type(
                'psu', current_build['total_power_consumption']
            )
        else:
            logger.warning(f"Unknown component type: {component_type}")
            return None

        if not all_options:
            logger.warning(f"No options found in database for {component_type}")
            return None

        # --- Filter: price range + must be a genuine upgrade -----------------
        candidates = []
        for opt in all_options:
            price = opt['price_usd']

            # Must cost more than the current part (it's an upgrade, not a swap)
            if price <= current_price + UpgradeEngine._MIN_PRICE_DELTA:
                continue

            # Must fit within the allocation-aware ceiling
            if price > effective_ceiling:
                continue

            # Component-specific upgrade quality gates
            if component_type == 'ram':
                mobo_max = current_build['motherboard'].get('max_memory_speed')
                current_eff = min(current_component['speed_mhz'], mobo_max) if mobo_max else current_component['speed_mhz']
                candidate_eff = min(opt['speed_mhz'], mobo_max) if mobo_max else opt['speed_mhz']
                is_capacity_upgrade = opt['capacity_gb'] > current_component['capacity_gb']
                is_speed_upgrade     = (
                    opt['capacity_gb'] == current_component['capacity_gb']
                    and candidate_eff > current_eff
                )
                if not (is_capacity_upgrade or is_speed_upgrade):
                    continue  # same capacity and no effective speed gain

            elif component_type == 'storage_primary':
                is_capacity_upgrade = opt['capacity_gb'] > current_component['capacity_gb']
                is_speed_upgrade     = (
                    opt['capacity_gb'] == current_component['capacity_gb']
                    and opt['seq_read_mbs'] > current_component['seq_read_mbs']
                )
                if not (is_capacity_upgrade or is_speed_upgrade):
                    continue

            elif component_type == 'cooler':
                if opt['tdp_rating'] <= current_component['tdp_rating']:
                    continue  # not a performance improvement

            elif component_type == 'psu':
                if opt['wattage'] < current_component['wattage']:
                    continue  # never suggest downgrading wattage

            # Hard compatibility gate
            ok, reason = UpgradeEngine._passes_compatibility(opt, component_type, current_build)
            if not ok:
                logger.debug(f"Filtered {opt.get('model')} — {reason}")
                continue

            candidates.append(opt)

        if not candidates:
            logger.warning(f"No compatible upgrade candidates for {component_type}")
            return None

        logger.info(f"Evaluating {len(candidates)} candidates for {component_type}")

        # --- Score and rank by performance-per-dollar ------------------------
        scored: List[Tuple[Dict, float]] = []
        for opt in candidates:
            value = UpgradeEngine._score_candidate(opt, component_type, current_build, build_type)
            scored.append((opt, value))
            logger.debug(
                f"  {opt.get('model')} ${opt['price_usd']} → "
                f"value={value:.4f}"
            )

        # Primary sort: value density descending; tiebreak: lower price first
        # (cheaper option that gives equal gain is objectively better value)
        scored.sort(key=lambda x: (-x[1], x[0]['price_usd']))

        # Attach balance warning to each candidate dict (non-destructive copy)
        import copy
        result = []
        for opt, _ in scored[:3]:
            enriched = copy.copy(opt)
            warning = UpgradeEngine._check_balance_warning(
                opt, component_type, current_build, build_type
            )
            enriched['balance_warning'] = warning  # None or a warning string
            result.append(enriched)

        logger.info(f"Returning {len(result)} ranked upgrade options for {component_type}")
        return result

    @staticmethod
    def apply_upgrade(
        current_build: Dict,
        component_type: str,
        new_component: Dict,
        budget: int,
    ) -> Optional[Dict]:
        """
        Apply an upgrade to the build, verify it stays within budget, and
        recalculate all derived values (total cost, remaining budget,
        performance score, and balance warnings).

        Returns the upgraded build dict, or None if the upgrade would exceed
        the total budget.
        """
        try:
            import copy
            upgraded_build = copy.deepcopy(current_build)

            # Swap the component (strip the transient 'balance_warning' key we
            # added in get_compatible_upgrades before storing in the build)
            stored_component = {k: v for k, v in new_component.items() if k != 'balance_warning'}
            upgraded_build[component_type] = stored_component

            # Recalculate total cost across all eight component slots
            component_keys = ['cpu', 'motherboard', 'ram', 'cooler', 'gpu',
                               'storage_primary', 'case', 'psu']
            upgraded_build['total_cost'] = sum(
                upgraded_build[k]['price_usd']
                for k in component_keys
                if upgraded_build.get(k)
            )

            if upgraded_build['total_cost'] > budget:
                logger.warning(
                    f"Upgrade would exceed budget: "
                    f"${upgraded_build['total_cost']} > ${budget}"
                )
                return None

            upgraded_build['remaining_budget'] = budget - upgraded_build['total_cost']

            # Recalculate performance score using the build-type config
            build_type = current_build.get('build_type', 'gaming')
            config = BUILD_CONFIGS[build_type]
            upgraded_build['performance_score'] = PerformanceScorer.calculate_overall_score(
                upgraded_build, config
            )

            # Re-run balance check and update warnings list
            is_balanced, reason = BalanceValidator.is_balanced(
                upgraded_build['cpu'],
                upgraded_build['gpu'],
                upgraded_build['motherboard'],
                build_type,
            )
            if not is_balanced:
                upgraded_build.setdefault('balance_warnings', [])
                if f"⚠️ {reason}" not in upgraded_build['balance_warnings']:
                    upgraded_build['balance_warnings'].append(f"⚠️ {reason}")
            else:
                # Clear resolved warnings when the build becomes balanced again
                upgraded_build['balance_warnings'] = [
                    w for w in upgraded_build.get('balance_warnings', [])
                    if reason not in w
                ]

            logger.info(
                f"Upgrade applied: {component_type} → {stored_component.get('model')} "
                f"(${stored_component['price_usd']}). "
                f"New total: ${upgraded_build['total_cost']}, "
                f"score: {upgraded_build['performance_score']:.1f}"
            )
            return upgraded_build

        except Exception as e:
            logger.error(f"Error applying upgrade: {str(e)}")
            return None

# ============================================================================
# MESSAGE FORMATTERS
# ============================================================================

class MessageFormatter:
    """Formats messages for display."""

    @staticmethod
    def build_summary(build: Dict, budget: int, show_warnings: bool = True) -> str:
        """Format build summary."""
        if not build['cpu'] or not build['gpu']:
            error = build.get('error_message', 'Could not generate build.')
            return f"❌ Error: {error}"
        
        total = build['total_cost']
        remaining = build['remaining_budget']
        status = "✅ Under Budget!" if remaining >= 0 else "⚠️ Over Budget"
        color = "🟢" if remaining >= 0 else "🔴"
        
        summary = f"""
<b>🖥️ YOUR PC BUILD SUMMARY</b>

<b>📊 BUDGET BREAKDOWN</b>
Total Budget: ${budget:,} USD
Total Cost: ${total:,} USD
Remaining Budget: ${remaining:,} USD {color}
Budget Used: {(total/budget*100):.1f}%
{status}

<b>⭐ PERFORMANCE SCORE: {build.get('performance_score', 0):.1f}</b>

<b>⚡ POWER CONSUMPTION</b>
Total TDP: {build['total_power_consumption']}W (CPU + GPU)
Recommended PSU: {build['psu']['wattage']}W
Headroom: {build['psu']['wattage'] - build['total_power_consumption']}W

<b>🛒 SELECTED COMPONENTS</b>
• <b>CPU:</b> {build['cpu']['brand']} {build['cpu']['model']}
  Tier: {BalanceValidator.get_cpu_tier(build['cpu']).name} | {build['cpu']['cores']}C/{build['cpu']['threads']}T | {build['cpu']['boost_ghz']} GHz
  💰 ${build['cpu']['price_usd']} ({(build['cpu']['price_usd']/budget*100):.1f}%)

• <b>Motherboard:</b> {build['motherboard']['brand']} {build['motherboard']['model']}
  Max RAM Speed: {build['motherboard'].get('max_memory_speed', 'N/A')} MHz
  💰 ${build['motherboard']['price_usd']} ({(build['motherboard']['price_usd']/budget*100):.1f}%)

• <b>RAM:</b> {build['ram']['brand']} {build['ram']['model']}
  {build['ram']['capacity_gb']}GB {build['ram']['type']} @ {build['ram']['speed_mhz']} MHz
  💰 ${build['ram']['price_usd']} ({(build['ram']['price_usd']/budget*100):.1f}%)

• <b>Cooler:</b> {build['cooler']['brand']} {build['cooler']['model']}
  💰 ${build['cooler']['price_usd']}

• <b>GPU:</b> {build['gpu']['brand']} {build['gpu']['model']}
  Tier: {BalanceValidator.get_gpu_tier(build['gpu']).name} | {build['gpu']['memory_gb']}GB | PCIe Gen {build['gpu'].get('pcie_gen', '?')}
  💰 ${build['gpu']['price_usd']} ({(build['gpu']['price_usd']/budget*100):.1f}%)

• <b>Storage:</b> {build['storage_primary']['brand']} {build['storage_primary']['model']}
  {build['storage_primary']['capacity_gb']}GB | {build['storage_primary']['seq_read_mbs']} MB/s
  💰 ${build['storage_primary']['price_usd']}

• <b>Case:</b> {build['case']['brand']} {build['case']['model']}
  💰 ${build['case']['price_usd']}

• <b>PSU:</b> {build['psu']['brand']} {build['psu']['model']}
  {build['psu']['efficiency_rating']}
  💰 ${build['psu']['price_usd']}
"""
        
        if show_warnings and build.get('balance_warnings'):
            summary += f"\n<b>⚠️ BALANCE NOTES:</b>\n"
            for warning in build['balance_warnings']:
                summary += f"{warning}\n"
        
        summary += "\n✅ <b>All components are compatible!</b>"
        return summary

    @staticmethod
    def upgrade_options(component_type: str, options: List[Dict], current_build: Dict) -> str:
        """Format upgrade options for a specific component."""
        if not options:
            return f"❌ No compatible upgrades available for {component_type.upper()}"
        
        current_component = current_build[component_type]
        current_price = current_component['price_usd']
        
        message = f"""
<b>🔄 UPGRADE OPTIONS FOR {component_type.upper()}</b>

<b>Current Component:</b>
{current_component['brand']} {current_component['model']} - ${current_price}

<b>━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>AVAILABLE UPGRADES:</b>

"""
        
        for i, option in enumerate(options, 1):
            price_diff = option['price_usd'] - current_price
            
            if component_type == 'gpu':
                tier = BalanceValidator.get_gpu_tier(option)
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   Tier: {tier.name} | {option['memory_gb']}GB {option['memory_type']}
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
            elif component_type == 'cpu':
                tier = BalanceValidator.get_cpu_tier(option)
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   Tier: {tier.name} | {option['cores']}C/{option['threads']}T | {option['boost_ghz']} GHz
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
            elif component_type == 'ram':
                motherboard_max_speed = current_build['motherboard'].get('max_memory_speed')
                speed_note = ""
                if motherboard_max_speed and option['speed_mhz'] > motherboard_max_speed:
                    speed_note = f" (will run at {motherboard_max_speed} MHz due to motherboard limit)"
                
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   {option['capacity_gb']}GB @ {option['speed_mhz']} MHz | CAS {option['cas_latency']}{speed_note}
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
            elif component_type == 'storage_primary':
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   {option['capacity_gb']}GB | {option['seq_read_mbs']} MB/s
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
            elif component_type == 'cooler':
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   {option['type']} | TDP: {option['tdp_rating']}W
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
            elif component_type == 'psu':
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   {option['wattage']}W | {option['efficiency_rating']}
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
        
        message += f"""
<b>━━━━━━━━━━━━━━━━━━━━━━━</b>
📝 <b>How to upgrade:</b> Type <code>upgrade 1</code>, <code>upgrade 2</code>, or <code>upgrade 3</code>
🔙 Type <code>back</code> to return to main options
"""
        return message

    @staticmethod
    def full_details(build: Dict, budget: int) -> str:
        """Format complete build details."""
        if not build['cpu'] or not build['gpu']:
            return "❌ Error: Incomplete build."
        
        gpu_interface = f"PCIe Gen {build['gpu'].get('pcie_gen', '?')}"
        cpu_tier = BalanceValidator.get_cpu_tier(build['cpu'])
        gpu_tier = BalanceValidator.get_gpu_tier(build['gpu'])
        max_ram_capacity = build['motherboard'].get('max_ram_capacity_gb', 'N/A')
        ram_slots = build['motherboard'].get('ram_slots', 'N/A')
        ram_modules = build['ram'].get('modules', 1)
        motherboard_max_speed = build['motherboard'].get('max_memory_speed')
        ram_speed = build['ram'].get('speed_mhz')
        
        # Note if RAM is running below its rated speed due to motherboard limitation
        speed_note = ""
        if motherboard_max_speed and ram_speed > motherboard_max_speed:
            speed_note = f"\n   ⚠️ NOTE: RAM rated for {ram_speed} MHz but motherboard supports max {motherboard_max_speed} MHz\n   RAM will run at {motherboard_max_speed} MHz"
        
        return f"""
<b>════════════════════════════════════════</b>
<b>🖥️  COMPLETE PC BUILD CONFIGURATION</b>
<b>════════════════════════════════════════</b>

<b>📊 BUILD HEALTH</b>
Performance Score: {build.get('performance_score', 0):.1f}
CPU Tier: {cpu_tier.name}
GPU Tier: {gpu_tier.name}
Balance Status: ✅ BALANCED
Budget Usage: {(build['total_cost']/budget*100):.1f}%

<b>💰 BUDGET SUMMARY</b>
Total Budget: ${budget:,} USD
Total Cost: ${build['total_cost']:,} USD
Remaining: ${build['remaining_budget']:,} USD

<b>⚡ POWER CONSUMPTION</b>
CPU TDP: {build['cpu']['tdp']}W
GPU TDP: {build['gpu']['tdp']}W
Total System TDP: {build['total_power_consumption']}W
PSU Capacity: {build['psu']['wattage']}W
Headroom: {build['psu']['wattage'] - build['total_power_consumption']}W

<b>═══════════════════════════════════════</b>
<b>🔧 PROCESSOR (CPU)</b>
<b>═══════════════════════════════════════</b>
Brand: {build['cpu']['brand']}
Model: {build['cpu']['model']}
Tier: {cpu_tier.name}
Cores/Threads: {build['cpu']['cores']}C / {build['cpu']['threads']}T
Base Clock: {build['cpu']['base_ghz']} GHz
Boost Clock: {build['cpu']['boost_ghz']} GHz
Socket: {build['cpu']['socket']}
TDP: {build['cpu']['tdp']}W
Price: ${build['cpu']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>🛠️  MOTHERBOARD</b>
<b>═══════════════════════════════════════</b>
Brand: {build['motherboard']['brand']}
Model: {build['motherboard']['model']}
Chipset: {build['motherboard']['chipset']}
Socket: {build['motherboard']['socket']}
Form Factor: {build['motherboard']['form_factor']}
Memory Type: {build['motherboard']['memory_type']}
Max Memory Speed: {motherboard_max_speed} MHz
M.2 Slots: {build['motherboard']['m2_slots']}
RAM Configuration:
Max RAM Capacity: {max_ram_capacity}GB
Available RAM Slots: {ram_slots}
Price: ${build['motherboard']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>💾 RAM (MEMORY)</b>
<b>═══════════════════════════════════════</b>
Brand: {build['ram']['brand']}
Model: {build['ram']['model']}
Type: {build['ram']['type']}
Capacity: {build['ram']['capacity_gb']} GB
Rated Speed: {ram_speed} MHz
CAS Latency: {build['ram']['cas_latency']}
Modules in Use: {ram_modules} stick(s){speed_note}
Price: ${build['ram']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>❄️  CPU COOLER</b>
<b>═══════════════════════════════════════</b>
Brand: {build['cooler']['brand']}
Model: {build['cooler']['model']}
Type: {build['cooler']['type']}
TDP Rating: {build['cooler']['tdp_rating']}W
Price: ${build['cooler']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>🎮 GRAPHICS CARD (GPU)</b>
<b>═══════════════════════════════════════</b>
Brand: {build['gpu']['brand']}
Model: {build['gpu']['model']}
Tier: {gpu_tier.name}
VRAM: {build['gpu']['memory_gb']} GB {build['gpu']['memory_type']}
Bus Width: {build['gpu']['bus_width']}-bit
Interface: {gpu_interface}
TDP: {build['gpu']['tdp']}W
Price: ${build['gpu']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>💿 PRIMARY STORAGE</b>
<b>═══════════════════════════════════════</b>
Brand: {build['storage_primary']['brand']}
Model: {build['storage_primary']['model']}
Capacity: {build['storage_primary']['capacity_gb']} GB
Type: {build['storage_primary']['type']}
Sequential Read: {build['storage_primary']['seq_read_mbs']} MB/s
Price: ${build['storage_primary']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>🏢 PC CASE</b>
<b>═══════════════════════════════════════</b>
Brand: {build['case']['brand']}
Model: {build['case']['model']}
Form Factor: {build['case']['form_factor']}
Max GPU Length: {build['case']['max_gpu_length_mm']}mm
Price: ${build['case']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>🔌 POWER SUPPLY UNIT (PSU)</b>
<b>═══════════════════════════════════════</b>
Brand: {build['psu']['brand']}
Model: {build['psu']['model']}
Wattage: {build['psu']['wattage']}W
Efficiency Rating: {build['psu']['efficiency_rating']}
Price: ${build['psu']['price_usd']}

<b>════════════════════════════════════════</b>
✨ Build is perfectly balanced and optimized! ✨
<b>════════════════════════════════════════</b>
"""

# ============================================================================
# CONVERSATION HANDLERS
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the bot."""
    welcome = """
🖥️ Welcome to PC Build Assistant Bot! 🖥️

I'm here to help you build a PERFECTLY BALANCED PC within your budget.

Key Features:
✅ Smart GPU/CPU balancing
✅ Tier-based component matching
✅ No more weak GPUs with overkill CPUs!
✅ Upgrade individual components
✅ Full compatibility checking
✅ Performance scoring

🎮 Gaming: GPU gets 45% of budget
🎬 Content Creation: CPU gets 30% of budget

Let's get started! 💰

What's your PC build budget? (Enter amount in USD, e.g., 1500)
    """
    await update.message.reply_text(welcome)
    return BUDGET

async def get_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get budget from user."""
    try:
        budget = int(update.message.text)
        
        if budget < 800:
            await update.message.reply_text(
                "❌ Budget too low. Minimum budget is $800 USD.\n\nPlease enter a valid budget:"
            )
            return BUDGET
        
        if budget > 100000:
            await update.message.reply_text(
                "❌ Budget too high. Please enter a realistic amount (max $100,000):"
            )
            return BUDGET
        
        context.user_data['budget'] = budget
        logger.info(f"User set budget: ${budget}")
        
        build_type_msg = f"""
✅ Budget set to: ${budget:,} USD

Now, choose your build type:

🎮 <b>Gaming</b>
   → GPU gets 45% of budget
   → Balanced performance focus
   → High FPS gaming priority

🎬 <b>Content Creation</b>
   → CPU gets 30% of budget
   → RAM gets 25% of budget
   → Rendering & editing focus

Type: "Gaming" or "Content Creation"
        """
        await update.message.reply_text(build_type_msg, parse_mode='HTML')
        return BUILD_TYPE
        
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number (e.g., 1500)")
        return BUDGET

async def select_build_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle build type selection."""
    user_input = update.message.text.lower().strip()
    
    if 'gaming' in user_input:
        build_type = 'gaming'
    elif 'content' in user_input or 'creation' in user_input:
        build_type = 'content_creation'
    else:
        await update.message.reply_text(
            '❌ Invalid input. Type "Gaming" or "Content Creation"'
        )
        return BUILD_TYPE
    
    context.user_data['build_type'] = build_type
    config = BUILD_CONFIGS[build_type]
    
    logger.info(f"User selected: {build_type}")
    
    await update.message.reply_text(
        f"✅ Selected: {config['description']}\n\n"
        f"🔄 Generating balanced build...\n"
        f"⏳ Analyzing GPU/CPU balance...\n"
        f"⏳ Optimizing component selection..."
    )
    
    # Generate balanced build
    build = BuildGenerator.generate(
        budget=context.user_data['budget'],
        build_type=build_type,
        allocations=config['budget_allocation']
    )
    
    if not build.get('cpu') or not build.get('gpu'):
        error = build.get('error_message', 'Could not generate build.')
        await update.message.reply_text(
            f"❌ {error}\n\n"
            f"Minimum budget: $1,200 USD\n\n"
            f"Type /start to try again."
        )
        logger.warning(f"Build failed: {error}")
        return -1
    
    build['build_type'] = build_type
    context.user_data['build'] = build
    formatter = MessageFormatter()
    
    await update.message.reply_text(
        formatter.build_summary(build, context.user_data['budget']),
        parse_mode='HTML'
    )
    
    await update.message.reply_text(
        """
✨ <b>BUILD COMPLETE!</b>

<b>🔄 UPGRADE OPTIONS:</b>
What would you like to do?

Type a command:
• <code>upgrade gpu</code> - Upgrade Graphics Card
• <code>upgrade cpu</code> - Upgrade Processor
• <code>upgrade ram</code> - Upgrade Memory
• <code>upgrade cooler</code> - Upgrade CPU Cooler
• <code>upgrade storage</code> - Upgrade Storage
• <code>upgrade psu</code> - Upgrade Power Supply

Or:
• <code>details</code> - View full specifications
• <code>start</code> - Create a new build
        """,
        parse_mode='HTML'
    )
    return UPGRADE_MENU

async def upgrade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle upgrade menu selection."""
    user_input = update.message.text.lower().strip()
    
    build = context.user_data.get('build')
    budget = context.user_data.get('budget')
    
    if not build or not budget:
        await update.message.reply_text("❌ No build found. Type /start to create one.")
        return -1
    
    formatter = MessageFormatter()
    upgrade_engine = UpgradeEngine()
    
    if user_input.startswith('upgrade'):
        parts = user_input.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Usage: Type 'upgrade gpu', 'upgrade cpu', etc.")
            return UPGRADE_MENU
        
        component_type = parts[1]
        
        component_map = {
            'gpu': 'gpu',
            'cpu': 'cpu',
            'ram': 'ram',
            'cooler': 'cooler',
            'storage': 'storage_primary',
            'psu': 'psu'
        }
        
        if component_type not in component_map:
            await update.message.reply_text(
                f"❌ Invalid component. Valid options: {', '.join(component_map.keys())}"
            )
            return UPGRADE_MENU
        
        component_key = component_map[component_type]
        
        # Debug: Show current component info
        current = build[component_key]
        logger.info(f"Checking upgrades for {component_type}: current={current.get('model')} (${current['price_usd']})")
        logger.info(f"Budget remaining: ${budget - (build['total_cost'] - current['price_usd'])}")
        
        # Get upgrade options
        options = upgrade_engine.get_compatible_upgrades(build, component_key, budget)
        
        if not options:
            remaining = budget - (build['total_cost'] - current['price_usd'])
            await update.message.reply_text(
                f"❌ No compatible upgrades available for {component_type.upper()}\n\n"
                f"Current: {current['brand']} {current['model']} (${current['price_usd']})\n"
                f"Remaining budget: ${remaining}\n\n"
                f"Reason: All better options exceed your remaining budget or don't exist."
            )
            return UPGRADE_MENU
        
        # Store options in context for next step
        context.user_data['upgrade_options'] = options
        context.user_data['upgrade_component'] = component_key
        
        # Show upgrade options
        upgrade_msg = formatter.upgrade_options(component_key, options, build)
        await update.message.reply_text(upgrade_msg, parse_mode='HTML')
        return UPGRADE_SELECTION
    
    elif 'detail' in user_input:
        detailed_msg = formatter.full_details(build, budget)
        
        if len(detailed_msg) > 4096:
            parts = [detailed_msg[i:i+4096] for i in range(0, len(detailed_msg), 4096)]
            for part in parts:
                await update.message.reply_text(part, parse_mode='HTML')
        else:
            await update.message.reply_text(detailed_msg, parse_mode='HTML')
        
        await update.message.reply_text(
            "✨ Type an upgrade command or /start for a new build.",
            parse_mode='HTML'
        )
        return UPGRADE_MENU
    
    elif 'start' in user_input or 'new' in user_input:
        return await start(update, context)
    
    else:
        await update.message.reply_text(
            """
❌ Invalid command. Type one of:
• <code>upgrade gpu</code>
• <code>upgrade cpu</code>
• <code>upgrade ram</code>
• <code>upgrade cooler</code>
• <code>upgrade storage</code>
• <code>upgrade psu</code>
• <code>details</code>
        """,
            parse_mode='HTML'
        )
        return UPGRADE_MENU

async def upgrade_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle upgrade selection."""
    user_input = update.message.text.lower().strip()
    
    build = context.user_data.get('build')
    budget = context.user_data.get('budget')
    options = context.user_data.get('upgrade_options', [])
    component_key = context.user_data.get('upgrade_component')
    
    if not build or not budget:
        await update.message.reply_text("❌ No build found. Type /start to create one.")
        return -1
    
    formatter = MessageFormatter()
    upgrade_engine = UpgradeEngine()
    
    if user_input.startswith('upgrade'):
        parts = user_input.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Usage: Type 'upgrade 1', 'upgrade 2', or 'upgrade 3'")
            return UPGRADE_SELECTION
        
        try:
            option_index = int(parts[1]) - 1
            if option_index < 0 or option_index >= len(options):
                await update.message.reply_text(
                    f"❌ Invalid selection. Choose 1-{len(options)}"
                )
                return UPGRADE_SELECTION
            
            selected_option = options[option_index]
            
            # Apply upgrade
            upgraded_build = upgrade_engine.apply_upgrade(
                build,
                component_key,
                selected_option,
                budget
            )
            
            if not upgraded_build:
                await update.message.reply_text(
                    "❌ Upgrade exceeds budget. Try a cheaper option."
                )
                return UPGRADE_SELECTION
            
            context.user_data['build'] = upgraded_build
            
            await update.message.reply_text("✅ Upgrade applied successfully!")
            await update.message.reply_text(
                formatter.build_summary(upgraded_build, budget),
                parse_mode='HTML'
            )
            
            await update.message.reply_text(
                """
<b>🔄 UPGRADE OPTIONS:</b>
What would you like to do next?

• <code>upgrade gpu</code> - Upgrade Graphics Card
• <code>upgrade cpu</code> - Upgrade Processor
• <code>upgrade ram</code> - Upgrade Memory
• <code>upgrade cooler</code> - Upgrade CPU Cooler
• <code>upgrade storage</code> - Upgrade Storage
• <code>upgrade psu</code> - Upgrade Power Supply
• <code>details</code> - View full specifications
• <code>start</code> - Create a new build
                """,
                parse_mode='HTML'
            )
            return UPGRADE_MENU
        
        except (ValueError, IndexError):
            await update.message.reply_text(
                f"❌ Invalid input. Use 'upgrade 1', 'upgrade 2', or 'upgrade 3'"
            )
            return UPGRADE_SELECTION
    
    elif 'back' in user_input:
        await update.message.reply_text("🔙 Returning to upgrade menu...")
        await update.message.reply_text(
            """
<b>🔄 UPGRADE OPTIONS:</b>

• <code>upgrade gpu</code> - Upgrade Graphics Card
• <code>upgrade cpu</code> - Upgrade Processor
• <code>upgrade ram</code> - Upgrade Memory
• <code>upgrade cooler</code> - Upgrade CPU Cooler
• <code>upgrade storage</code> - Upgrade Storage
• <code>upgrade psu</code> - Upgrade Power Supply
• <code>details</code> - View full specifications
            """,
            parse_mode='HTML'
        )
        return UPGRADE_MENU
    
    else:
        await update.message.reply_text(
            f"❌ Invalid input. Type 'upgrade 1', 'upgrade 2', 'upgrade 3', or 'back'"
        )
        return UPGRADE_SELECTION

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help."""
    help_text = """
<b>🖥️ PC BUILD ASSISTANT - HELP</b>

<b>Commands:</b>
/start - Start building a PC
/help - Show this message
/about - About the bot

<b>How to Use:</b>
1. Type /start
2. Enter your total budget
3. Choose build type (Gaming or Content Creation)
4. Review the generated build
5. Upgrade components if desired
6. Type "details" for full specifications

<b>Build Types:</b>
🎮 <b>Gaming:</b> GPU-focused, 45% budget
🎬 <b>Content Creation:</b> CPU+RAM focused, 30%+25%

<b>What's New:</b>
✨ Smart GPU/CPU balancing
✨ Tier-based component matching
✨ Individual component upgrades
✨ Full compatibility checking

Minimum Budget: $800 USD
    """
    await update.message.reply_text(help_text, parse_mode='HTML')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show about."""
    about_text = """
<b>About PC Build Assistant Bot</b>

Version 6.1 - Motherboard Memory Speed Integration

<b>🎯 Core Features:</b>
✅ GPU/CPU balance enforcement
✅ Tier-based component matching
✅ Performance scoring system
✅ Smart budget allocation
✅ Individual component upgrades
✅ Full compatibility checking
✅ Power consumption analysis
✅ Motherboard memory speed awareness

<b>🆕 New in 6.1:</b>
🔹 Motherboard max_memory_speed fetching
🔹 RAM speed compatibility checking
🔹 Speed limitation alerts in upgrade options
🔹 Effective speed calculation for scoring
🔹 Build details show speed limits
🔹 Smart RAM selection based on board limits

<b>📊 How It Works:</b>
1. Selects CPU first based on tier
2. Calculates expected GPU tier for that CPU
3. Filters GPUs by matching tier
4. Fetches motherboard max memory speed
5. Selects RAM with board speed in mind
6. Alerts if RAM faster than motherboard limit
7. Ensures all components work together
8. Validates compatibility at each step

Built with ❤️ for balanced PC builds
    """
    await update.message.reply_text(about_text, parse_mode='HTML')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation."""
    await update.message.reply_text("Cancelled. Type /start to begin again.")
    return -1

# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not found in .env")
        print("❌ BOT_TOKEN not found! Set it in .env file")
        return
    
    if not load_database():
        logger.error("❌ Failed to load database")
        return
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_budget)],
            BUILD_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_build_type)],
            UPGRADE_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, upgrade_menu)],
            UPGRADE_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, upgrade_selection)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('about', about_command))
    
    logger.info("🤖 Balanced Build Bot ready!")
    print("🤖 Bot started and listening...")
    application.run_polling()

if __name__ == '__main__':
    main()
