package scheduler.db;

import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;
import redis.clients.jedis.JedisPoolConfig;

public class RedisManager {
    private static final JedisPool jedisPool;

    static {
        JedisPoolConfig poolConfig = new JedisPoolConfig();
        poolConfig.setMaxTotal(50); // Maximum active connections
        poolConfig.setMaxIdle(10);  // Maximum idle connections
        poolConfig.setMinIdle(2);   // Minimum idle connections
        poolConfig.setTestOnBorrow(true); // Validate connection before using
        
        // Connect to Redis. Read endpoint from environment variable if available.
        String redisHost = System.getenv("RedisEndpoint");
        if (redisHost == null || redisHost.isEmpty()) {
            redisHost = "localhost";
        }
        jedisPool = new JedisPool(poolConfig, redisHost, 6379);
    }

    /**
     * Get a Jedis connection from the pool.
     * Usage: try (Jedis jedis = RedisManager.getJedis()) { ... }
     */
    public static Jedis getJedis() {
        return jedisPool.getResource();
    }
    
    /**
     * Gracefully close the pool when application shuts down
     */
    public static void closePool() {
        if (jedisPool != null && !jedisPool.isClosed()) {
            jedisPool.close();
        }
    }
}
