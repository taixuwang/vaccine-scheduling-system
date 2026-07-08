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
        
        // Connect to local Redis (assuming default port 6379, no password)
        // If your Redis has a password, use: new JedisPool(poolConfig, "localhost", 6379, 2000, "yourpassword");
        jedisPool = new JedisPool(poolConfig, "localhost", 6379);
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
